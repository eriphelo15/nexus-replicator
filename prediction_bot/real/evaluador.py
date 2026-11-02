"""Evalúa versiones del modelo de probabilidad contra el mercado con datos REALES del bot en sombra.

Métrica: Brier (error cuadrático medio de la probabilidad de cada tramo). Mercado ≈ 0,042; modelo actual ≈ 0,054.
Todo es walk-forward: para un día D solo se usan días anteriores a D-1 para aprender sesgos y errores.

    python evaluador.py DIR
"""
import bisect, gzip, json, math, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

H = 3600
RAIZ = Path(__file__).parent.parent
EST = json.loads((RAIZ / "sombra" / "estaciones.json").read_text())
_erf = np.frompyfunc(math.erf, 1, 1)


def phi(x):
    return 0.5 * (1 + math.erf(float(x) / math.sqrt(2)))


class Datos:
    def __init__(self, c, metar, nwp):
        e = EST[c]
        self.c, self.tz, self.f = c, ZoneInfo(e["tz"]), e["f"]
        obs = []
        for v, t in metar:
            ts = datetime.strptime(v, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
            obs.append((ts, round(t) if self.f else round((t - 32) / 1.8)))
        self.obs = sorted(obs); self.obs_t = [x[0] for x in self.obs]
        self.series = defaultdict(list)
        for k, d in nwp.items():
            m, run = k.split("|")
            vals = d["t"].get(c)
            if not vals:
                continue
            t0 = datetime.fromisoformat(run).replace(tzinfo=timezone.utc).timestamp()
            v = np.array(vals, float); v = v * 1.8 + 32 if self.f else v
            hs = np.array(d["pasos"], float)
            self.series[m].append((d["pub"], t0, np.interp(np.arange(0, hs[-1] + 1), hs, v)))
        for m in self.series:
            self.series[m].sort(key=lambda x: x[0])
        self.pubs = {m: [x[0] for x in l] for m, l in self.series.items()}

    def dia(self, d):
        ini = datetime.fromisoformat(d).replace(tzinfo=self.tz)
        return ini.astimezone(timezone.utc).timestamp(), (ini + timedelta(days=1)).astimezone(timezone.utc).timestamp()

    def obs_entre(self, a, b):
        return self.obs[bisect.bisect_left(self.obs_t, a):bisect.bisect_left(self.obs_t, b)]

    def rasgos(self, d, t):
        """Rasgos en el instante t para el día d: máximo previsto restante por modelo, ya medido y anomalía actual."""
        a, b = self.dia(d)
        out = {}
        anoms = []
        vistos = self.obs_entre(a - 6 * H, t - 300)
        for m in ("gfs", "ecmwf"):
            i = bisect.bisect_right(self.pubs.get(m, []), t) - 1
            if i < 0:
                return None
            _, t0, vals = self.series[m][i]
            k0 = int((math.ceil(max(a, t) / H) * H - t0) // H); k1 = int((b - t0) // H)
            if k0 < 0 or k1 > len(vals) or k0 >= k1:
                return None
            out[m] = float(np.max(vals[k0:k1]))
            if vistos:                                   # anomalía: última medición menos previsión a esa hora
                to, vo = vistos[-1]
                k = int(round((to - t0) / H))
                if 0 <= k < len(vals) and t - to < 2 * H:
                    anoms.append(vo - vals[k])
        hoy = [v for ts, v in vistos if ts >= a]
        out["ya"] = max(hoy) if hoy else None
        out["anom"] = float(np.mean(anoms)) if anoms else 0.0
        out["h_rest"] = (b - max(a, t)) / H
        return out

    def real(self, d):
        a, b = self.dia(d)
        o = self.obs_entre(a, b)
        return max(v for _, v in o) if len(o) >= 18 else None


def fase_t(b, f):
    return ((b - f * H) // H) * H + 600


def entrenar(datos, dias_ent):
    """Tabla de entrenamiento: (ciudad, día, fase) → rasgos + máximo real de las horas restantes."""
    tabla = []
    for c, D in datos.items():
        for d in dias_ent:
            real = D.real(d)
            if real is None:
                continue
            a, b = D.dia(d)
            for f in range(1, 61):
                t = fase_t(b, f)
                r = D.rasgos(d, t)
                if not r:
                    continue
                resto = [v for _, v in D.obs_entre(max(a, t - 300), b)]
                if not resto:
                    continue
                tabla.append(dict(c=c, d=d, f=f, rmax=max(resto), real=real, **r))
    return tabla


def prob_tramos(mu, sigma, ya, tramos):
    """X = max(ya, N(mu, sigma)) redondeado; prob. de cada tramo (lo, hi)."""
    out = []
    for lo, hi in tramos:
        l, h = lo - 0.5, hi + 0.5
        ch = 1.0 if hi >= 900 else float(phi((h - mu) / sigma))
        cl = 0.0 if lo <= -900 else float(phi((l - mu) / sigma))
        if ya is not None and ya >= h:
            p = 0.0
        elif ya is not None and ya >= l:
            p = ch
        else:
            p = ch - cl
        out.append(max(min(p, 1.0), 0.0))
    s = sum(out)
    return [x / s for x in out] if s > 0 else out


class Version:
    """Modelo gaussiano: mu = combinación de modelos + sesgo + k·anomalía; sigma por fase y ciudad."""

    def __init__(self, peso_ecm=0.5, usar_anom=False, ventana=45, por_ciudad=True, escala=1.0):
        self.w, self.anom, self.ventana, self.pc, self.escala = peso_ecm, usar_anom, ventana, por_ciudad, escala

    def base(self, r):
        return self.w * r["ecmwf"] + (1 - self.w) * r["gfs"]

    def ajustar(self, filas):
        """Por fase: regresión residuo ~ a + k·anom (todas las ciudades); por ciudad y fase: sesgo y desviación."""
        self.k = {}
        porf = defaultdict(list)
        for x in filas:
            porf[x["f"]].append(x)
        for f, xs in porf.items():
            res = np.array([x["rmax"] - self.base(x) for x in xs]); an = np.array([x["anom"] for x in xs])
            self.k[f] = float(np.polyfit(an, res, 1)[0]) if self.anom and np.std(an) > 0.1 and len(xs) > 50 else 0.0
        self.sesgo, self.sd = {}, {}
        grupos = defaultdict(list)
        for x in filas:
            e = x["rmax"] - self.base(x) - self.k.get(x["f"], 0) * x["anom"]
            grupos[(x["c"] if self.pc else "*", x["f"])].append(e)
            grupos[("*", x["f"])].append(e)
        for g, es in grupos.items():
            self.sesgo[g] = float(np.mean(es)); self.sd[g] = max(float(np.std(es)), 0.6)

    def probs(self, r, f, c, tramos):
        g = (c, f) if self.pc and len([1]) else ("*", f)
        g = g if g in self.sesgo else ("*", f)
        mu = self.base(r) + self.k.get(f, 0) * r["anom"] + self.sesgo.get(g, 0)
        sd = self.sd.get(g, 2.0) * self.escala
        return prob_tramos(mu, sd, r["ya"], tramos)


def main(dirp):
    metar = json.loads((dirp / "metar.json").read_text())
    nwp = {}
    for p in (RAIZ / "bilberry" / "data" / "nwp.json", dirp / "nwp_rec.json"):
        nwp.update(json.loads(p.read_text()))
    datos = {c: Datos(c, metar[c], nwp) for c in EST if c in metar}
    res = json.loads((dirp / "resoluciones.json").read_text())
    filas = defaultdict(list)                     # (c, d, t, fase) → [(lo, p_bot, medio, gana)]
    for l in gzip.open(dirp / "registro.jsonl.gz", "rt"):
        r = json.loads(l)
        g = res.get(f"{r['c']}|{r['d']}", {}).get(str(r["lo"]))
        if g is None or r["medio"] is None or not r["vivo"]:
            continue
        filas[(r["c"], r["d"], r["t"], r["fase"])].append((r["lo"], r["p"], r["medio"], g))
    dias_eval = sorted({k[1] for k in filas})
    print("días evaluados:", dias_eval[0], "→", dias_eval[-1], " grupos:", len(filas))

    # tramos (lo, hi) de cada evento
    los = defaultdict(set)
    for (c, d, t, f), xs in filas.items():
        for lo, *_ in xs:
            los[(c, d)].add(lo)
    hi_de = {}
    for (c, d), s in los.items():
        s = sorted(s)
        for i, lo in enumerate(s):
            if i == len(s) - 1:
                hi_de[(c, d, lo)] = 999
            elif lo == -999:
                hi_de[(c, d, lo)] = s[i + 1] - 1
            else:
                hi_de[(c, d, lo)] = lo + (1 if EST[c]["f"] else 0)

    ini_ent = (datetime.fromisoformat(dias_eval[0]) - timedelta(days=60)).date()
    todos_dias = [(ini_ent + timedelta(days=i)).isoformat() for i in range((datetime.fromisoformat(dias_eval[-1]).date() - ini_ent).days + 1)]
    print("entrenando con", todos_dias[0], "→", todos_dias[-1], "…", flush=True)
    tabla = entrenar(datos, todos_dias)
    print("filas de entrenamiento:", len(tabla))

    versiones = {
        "V1 media 50/50, sesgo+desv. por ciudad": Version(0.5, False),
        "V2 ECMWF 70 %": Version(0.7, False),
        "V3 ECMWF 70 % + anomalía actual": Version(0.7, True),
        "V3 con desviación ×0,7": Version(0.7, True, escala=0.7),
        "V3 con desviación ×0,85": Version(0.7, True, escala=0.85),
        "V3 con desviación ×1,2": Version(0.7, True, escala=1.2),
    }
    acum = {n: [0.0, 0] for n in versiones}
    acum_f = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    bot = mer = 0.0; n = 0
    for d in dias_eval:
        limite = (datetime.fromisoformat(d) - timedelta(days=1)).date().isoformat()
        desde = (datetime.fromisoformat(d) - timedelta(days=46)).date().isoformat()
        ent = [x for x in tabla if desde <= x["d"] < limite]
        for v in versiones.values():
            v.ajustar(ent)
        for (c, dd, t, f), xs in filas.items():
            if dd != d:
                continue
            r = datos[c].rasgos(d, t)
            if not r:
                continue
            tr = [(lo, hi_de[(c, d, lo)]) for lo, *_ in xs]
            for nombre, v in versiones.items():
                ps = v.probs(r, f, c, tr)
                acum[nombre][0] += sum((p - x[3]) ** 2 for p, x in zip(ps, xs)); acum[nombre][1] += len(xs)
            ps3 = versiones["V3 ECMWF 70 % + anomalía actual"].probs(r, f, c, tr)
            for alfa in (0.1, 0.2, 0.3):
                mz = acum.setdefault(f"mezcla {alfa:.0%} modelo + mercado", [0.0, 0])
                mz[0] += sum((alfa * p + (1 - alfa) * x[2] - x[3]) ** 2 for p, x in zip(ps3, xs)); mz[1] += len(xs)
            for p, (lo, pb, md, g) in zip(ps3, xs):
                bot += (pb - g) ** 2; mer += (md - g) ** 2; n += 1
                fb = "≤12h" if f <= 12 else "12-24h" if f <= 24 else "24-36h" if f <= 36 else ">36h"
                a = acum_f[fb]; a[0] += (p - g) ** 2; a[1] += (md - g) ** 2; a[2] += (pb - g) ** 2; a[3] += 1
    print(f"\nBrier (menor = mejor), {n} observaciones:")
    print(f"  {'Mercado':42} {mer / n:.4f}")
    print(f"  {'Modelo actual del bot':42} {bot / n:.4f}")
    for nombre, (s, k) in acum.items():
        print(f"  {nombre:42} {s / k:.4f}")
    print("\nV3 por antelación (modelo / mercado / bot actual):")
    for fb in ("≤12h", "12-24h", "24-36h", ">36h"):
        a = acum_f[fb]
        print(f"  {fb:7} {a[0] / a[3]:.4f} / {a[1] / a[3]:.4f} / {a[2] / a[3]:.4f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
