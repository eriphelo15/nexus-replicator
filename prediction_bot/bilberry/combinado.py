"""Prueba combinada: temperatura medida (METAR) + previsiones de 7 modelos, decisión cada hora a hh:10 UTC.

Para cada mercado (máxima o mínima del día D en una ciudad) y cada hora desde 36 h antes hasta el final de D:
  1. extremo medido hasta ahora en D (si D ya empezó), con datos publicados 5 min antes
  2. extremo previsto para las horas que quedan de D = media de 7 modelos, usando SOLO la ejecución que ya
     existía: la de ~1 día antes para horas a ≤18 h vista, la de ~2 días antes para horas a ≤42 h vista
  3. error histórico de esa previsión, a la misma antelación, en los 30 días anteriores de esa ciudad
     (walk-forward, sin mirar el futuro) → probabilidad de cada tramo
  4. compra SÍ o NO si la probabilidad se aleja del precio ≥ MARGEN; versión con ventas: cierra cuando
     el precio supera a la probabilidad (ventaja recogida o perdida)
Apuesta fija 25 $, +1 céntimo de deslizamiento, 1,7 % de comisión en cada compra/venta.

    python combinado.py
"""
import bisect, json, math, random, re, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

DATA = Path(__file__).parent / "data"
APUESTA, COMISION = 25.0, 0.017
DESLIZ = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
VENTANA, MIN_POOL, SUAVIZADO = 30, 12, 0.6
SUMA = (0.9, 1.15)
import os
RETRASO_PRECIO = int(os.environ.get("RETRASO_PRECIO", "0"))
H = 3600


def a_unidad(tmpf, fah):
    return round(tmpf) if fah else round((tmpf - 32) / 1.8)


def tramo(q):
    n = [int(x) for g in re.findall(r"(-?\d+)\s*-\s*(-?\d+)°|(-?\d+)°", q) for x in g if x]
    if "or below" in q: return (-999, n[0])
    if "or higher" in q or "or above" in q: return (n[0], 999)
    return (n[0], n[-1])


def phi(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


class Ciudad:
    def __init__(self, e, metar, prev):
        self.tz, self.f = ZoneInfo(e["tz"]), e["f"]
        self.obs = sorted((datetime.strptime(v, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp(),
                           a_unidad(t, self.f)) for v, t in metar)
        self.obs_t = [x[0] for x in self.obs]
        t0 = datetime.fromisoformat(prev["time"][0]).replace(tzinfo=timezone.utc).timestamp()
        self.t0 = t0
        self.fc = {}
        for lag in (1, 2):
            cols = [np.array([np.nan if v is None else v for v in prev[k]], float)
                    for k in prev if f"previous_day{lag}_" in k]
            self.fc[lag] = np.nanmean(np.vstack(cols), axis=0)

    def dia(self, d):
        ini = datetime.fromisoformat(d).replace(tzinfo=self.tz)
        return ini.astimezone(timezone.utc).timestamp(), (ini + timedelta(days=1)).astimezone(timezone.utc).timestamp()

    def obs_entre(self, a, b):
        i, j = bisect.bisect_left(self.obs_t, a), bisect.bisect_left(self.obs_t, b)
        return [x[1] for x in self.obs[i:j]]

    def prevision(self, t, a, b, signo):
        """Extremo previsto (en signo: +1 máx, −1 mín → se maneja como máximo de signo·T) en horas [a, b)."""
        vals = []
        v = math.ceil(max(a, t) / H) * H
        while v < b:
            k = int((v - self.t0) // H)
            ade = (v - t) / H
            lag = 1 if ade <= 18 else 2 if ade <= 42 else None
            if lag is None or k < 0 or k >= len(self.fc[lag]) or np.isnan(self.fc[lag][k]):
                return None
            vals.append(signo * self.fc[lag][k]); v += H
        return max(vals) if vals else None


def preparar():
    est = json.loads((DATA / "estaciones.json").read_text())
    metar = json.loads((DATA / "metar.json").read_text())
    prev = json.loads((DATA / "prev_horarias.json").read_text())
    return {c: Ciudad(est[c], metar[c], prev[c]) for c in est if c in metar and c in prev}


def residuos(ciu, signo):
    """Error de la previsión, por día y por horas que faltan para el final del día (fase 1..60)."""
    out = defaultdict(dict)   # fase → {día: residuo}
    dias = sorted({datetime.fromtimestamp(t, ciu.tz).date().isoformat() for t in ciu.obs_t})
    for d in dias:
        a, b = ciu.dia(d)
        todo = ciu.obs_entre(a, b)
        if len(todo) < 18:
            continue
        for fase in range(1, 61):
            t = b - fase * H + 10 * 60 - H          # hh:10 UTC
            t = (t // H) * H + 600
            resto = ciu.obs_entre(max(a, t - 300), b)
            f = ciu.prevision(t, a, b, signo)
            if f is None or not resto:
                continue
            out[fase][d] = max(signo * x for x in resto) - f
    return out


def simular(ciudades, mercados, margen=0.10, ventas=False, pmin=0.03, pmax=0.97, registro=None):
    pools = {}
    ops = []
    for m in mercados:
        c, d, tipo = m["ciudad"], m["dia"], m["tipo"]
        if c not in ciudades:
            continue
        ciu = ciudades[c]; signo = 1 if tipo == "highest" else -1
        if (c, signo) not in pools:
            pools[(c, signo)] = residuos(ciu, signo)
        pool = pools[(c, signo)]
        a, b = ciu.dia(d)
        tramos = []
        for t in m["tramos"]:
            lo, hi = tramo(t["q"])
            if signo < 0:
                lo, hi = -hi, -lo
            if t["precios"]:
                tramos.append(dict(lo=lo, hi=hi, gana=t["gana"], pt=[x[0] for x in t["precios"]],
                                   pp=[x[1] for x in t["precios"]], pos=None))
        if not tramos or sum(t["gana"] for t in tramos) != 1:
            continue
        limite = (datetime.fromisoformat(d) - timedelta(days=1)).date().isoformat()
        for fase in range(60, 0, -1):
            t = b - fase * H
            t = (t // H) * H + 600
            if t >= b:
                continue
            f = ciu.prevision(t, a, b, signo)
            res = [v for dd, v in pool.get(fase, {}).items() if dd < limite][-VENTANA:]
            if f is None or len(res) < MIN_POOL:
                continue
            vistos = ciu.obs_entre(a, t - 300)
            ya = max(signo * x for x in vistos) if vistos else -1e9
            centros = f + np.array(res)
            # mercado "vivo": la suma de precios de todos los tramos ronda 1 (si no, son precios de relleno)
            actuales = []
            for tr in tramos:
                i = bisect.bisect_right(tr["pt"], t - RETRASO_PRECIO) - 1
                actuales.append(tr["pp"][i] if i >= 0 else None)
            if None in actuales or not (SUMA[0] <= sum(actuales) <= SUMA[1]):
                continue
            for tr in tramos:
                lo, hi = tr["lo"] - 0.5, tr["hi"] + 0.5
                # X = max(ya, N(centro, s)); P(lo ≤ X < hi)
                cdf_hi = phi((hi - centros) / SUAVIZADO) if hi < 900 else np.ones_like(centros)
                cdf_lo = phi((lo - centros) / SUAVIZADO) if lo > -900 else np.zeros_like(centros)
                if ya >= hi:
                    p = 0.0
                elif ya >= lo:
                    p = float(np.mean(cdf_hi))
                else:
                    p = float(np.mean(cdf_hi - cdf_lo))
                i = bisect.bisect_right(tr["pt"], t - RETRASO_PRECIO) - 1
                if i < 0 or t - tr["pt"][i] > 3 * H:
                    continue
                precio = tr["pp"][i]
                if len(set(tr["pp"][:i + 1])) < 3:      # el precio aún no se ha movido: sin negociación real
                    continue
                if registro is not None:
                    registro.append((c, d, fase, p, precio, tr["gana"], tr["lo"], f))
                pos = tr["pos"]
                if pos is None:
                    if p - precio >= margen and pmin <= precio <= pmax:
                        coste = min(precio + DESLIZ, 0.995)
                        tr["pos"] = dict(lado="SI", coste=coste, acc=APUESTA / coste, t=t, fase=fase, p=p, precio=precio)
                    elif precio - p >= margen and pmin <= precio <= pmax:
                        coste = min(1 - precio + DESLIZ, 0.995)
                        tr["pos"] = dict(lado="NO", coste=coste, acc=APUESTA / coste, t=t, fase=fase, p=p, precio=precio)
                elif ventas and not pos.get("cerrada"):
                    valor = precio if pos["lado"] == "SI" else 1 - precio
                    justo = p if pos["lado"] == "SI" else 1 - p
                    if valor - DESLIZ > justo + 0.02:          # el mercado paga más de lo que vale → vender
                        pos.update(cerrada=True, cobro=pos["acc"] * (valor - DESLIZ) * (1 - COMISION))
        for tr in tramos:
            pos = tr["pos"]
            if not pos:
                continue
            gana = tr["gana"] if pos["lado"] == "SI" else not tr["gana"]
            cobro = pos["cobro"] if pos.get("cerrada") else pos["acc"] * gana
            ops.append(dict(c=c, d=d, tipo=tipo, lado=pos["lado"], fase=pos["fase"], precio=pos["precio"],
                            p=pos["p"], g=cobro - APUESTA * (1 + COMISION), cerrada=bool(pos.get("cerrada"))))
    return ops


def informe(nombre, xs):
    if not xs:
        print(f"{nombre:34} sin operaciones"); return
    g = sum(x["g"] for x in xs)
    dias = defaultdict(float)
    for x in xs: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
    print(f"{nombre:34} ops {len(xs):5}  ganancia {g:+8.0f} $  por apuesta {g / len(xs) / APUESTA:+6.1%}  "
          f"aciertos {sum(x['g'] > 0 for x in xs) / len(xs):4.0%}  IC90 [{bs[50]:+.0f}, {bs[950]:+.0f}]")


def main():
    ciudades = preparar()
    mercados = json.loads((DATA / "mercados50.json").read_text())
    mercados.sort(key=lambda m: m["dia"])
    margen = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    for ventas in (False, True):
        ops = simular(ciudades, mercados, margen=margen, ventas=ventas)
        print(f"\n=== margen {margen:.2f}, {'CON ventas' if ventas else 'sin ventas (hasta resolución)'} ===")
        informe("TOTAL", ops)
        for k, f in [("lado SI", lambda o: o["lado"] == "SI"), ("lado NO", lambda o: o["lado"] == "NO"),
                     ("máximas", lambda o: o["tipo"] == "highest"), ("mínimas", lambda o: o["tipo"] == "lowest"),
                     ("durante el día (≤24 h)", lambda o: o["fase"] <= 24),
                     ("víspera (24-36 h)", lambda o: 24 < o["fase"] <= 36),
                     ("antes (>36 h)", lambda o: o["fase"] > 36),
                     ("precio < 20 c", lambda o: o["precio"] < 0.2), ("precio 20-60 c", lambda o: 0.2 <= o["precio"] < 0.6),
                     ("precio ≥ 60 c", lambda o: o["precio"] >= 0.6)]:
            informe("  " + k, [o for o in ops if f(o)])
        sem = defaultdict(list)
        for o in ops: sem[datetime.fromisoformat(o["d"]).strftime("%G-W%V")].append(o)
        for s in sorted(sem): informe("  semana " + s, sem[s])
        json.dump(ops, open(DATA / f"ops_combinado_{'ventas' if ventas else 'hold'}.json", "w"))


if __name__ == "__main__":
    main()
