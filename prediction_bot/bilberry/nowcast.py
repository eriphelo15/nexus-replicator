"""Prueba del sistema "durante el día": solo con la temperatura ya medida en el aeropuerto (METAR).

Cada hora (hh:10 UTC, como Bilberry) y para cada mercado de máxima del día en curso:
  1. máxima medida hasta ahora (hora local del aeropuerto)
  2. probabilidad de cada tramo = cuánto más subió la temperatura, a esa misma hora local,
     en los 30 días ANTERIORES de esa ciudad (distribución empírica, sin mirar el futuro)
  3. si la probabilidad supera al precio en ≥ MARGEN → comprar SÍ; si queda por debajo → comprar NO
Apuesta fija, deslizamiento y comisión incluidos. Se mantiene hasta la resolución.

    python nowcast.py
"""
import bisect, json, random, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).parent / "data"
APUESTA, DESLIZ, COMISION = 25, 0.01, 0.017
VENTANA = 30


def a_unidad(tmpf, fah):
    return round(tmpf) if fah else round((tmpf - 32) / 1.8)


def tramo(q):
    n = [int(x) for g in re.findall(r"(-?\d+)\s*-\s*(-?\d+)°|(-?\d+)°", q) for x in g if x]
    if "or below" in q: return (-999, n[0])
    if "or higher" in q or "or above" in q: return (n[0], 999)
    return (n[0], n[-1])


def series_diarias(est, metar):
    """Para cada ciudad y día local: lista horaria (hora local 0-23) de máxima acumulada, y máxima final."""
    out = {}
    for c, filas in metar.items():
        e = est[c]; tz = ZoneInfo(e["tz"]); dias = defaultdict(list)
        for v, t in filas:
            u = datetime.strptime(v, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            loc = u.astimezone(tz)
            dias[loc.date().isoformat()].append((u.timestamp(), loc.hour + loc.minute / 60, a_unidad(t, e["f"])))
        res = {}
        for d, xs in dias.items():
            xs.sort()
            if len(xs) < 18 or xs[0][1] > 2 or xs[-1][1] < 21:
                continue   # día incompleto
            res[d] = dict(obs=xs, maxi=max(x[2] for x in xs))
        out[c] = res
    return out


def main(margen=0.10, solo_hasta_hora=None, verbose=True):
    est = json.loads((DATA / "estaciones.json").read_text())
    metar = json.loads((DATA / "metar.json").read_text())
    mercados = [m for m in json.loads((DATA / "mercados50.json").read_text()) if m["tipo"] == "highest"]
    serie = series_diarias(est, metar)

    # 1) comprobar que la máxima medida coincide con el tramo ganador
    ok = tot = 0
    for m in mercados:
        s = serie.get(m["ciudad"], {}).get(m["dia"])
        gan = [t for t in m["tramos"] if t["gana"]]
        if not s or len(gan) != 1:
            continue
        a, b = tramo(gan[0]["q"]); tot += 1; ok += a <= s["maxi"] <= b
    print(f"Coincidencia máxima METAR vs tramo ganador: {ok}/{tot} = {ok / max(tot, 1):.0%}")
    malas = {c for c in est if sum(1 for m in mercados if m["ciudad"] == c) and
             (lambda r: r[1] and r[0] / r[1] < 0.85)(
                 [sum(1 for m in mercados if m["ciudad"] == c and serie.get(c, {}).get(m["dia"]) and
                      len([t for t in m["tramos"] if t["gana"]]) == 1 and
                      (lambda ab: ab[0] <= serie[c][m["dia"]]["maxi"] <= ab[1])(tramo([t for t in m["tramos"] if t["gana"]][0]["q"]))),
                  sum(1 for m in mercados if m["ciudad"] == c and serie.get(c, {}).get(m["dia"]) and
                      len([t for t in m["tramos"] if t["gana"]]) == 1)])}
    print("Ciudades excluidas (coincidencia < 85 %):", sorted(malas))

    ops = []
    for m in sorted(mercados, key=lambda x: x["dia"]):
        c, d = m["ciudad"], m["dia"]
        if c in malas or d not in serie.get(c, {}):
            continue
        e = est[c]; tz = ZoneInfo(e["tz"])
        previos = [serie[c][x] for x in sorted(serie[c]) if x < d][-VENTANA:]
        if len(previos) < 15:
            continue
        hoy = serie[c][d]
        ini = datetime.fromisoformat(d).replace(tzinfo=tz)
        ya = set()
        for hl in range(0, 24):
            t_dec = (ini + timedelta(hours=hl)).astimezone(timezone.utc)
            t_dec = t_dec.replace(minute=10, second=0)          # hh:10 UTC
            hloc = t_dec.astimezone(tz); hloc = hloc.hour + hloc.minute / 60
            if t_dec.astimezone(tz).date().isoformat() != d or (solo_hasta_hora and hloc > solo_hasta_hora):
                continue
            ts = t_dec.timestamp() - 5 * 60                      # dato publicado ~5 min antes
            vistos = [x for x in hoy["obs"] if x[0] <= ts]
            if not vistos:
                continue
            ms = max(x[2] for x in vistos)
            # subida restante en días anteriores a la misma hora local
            subidas = []
            for p in previos:
                o = [x[2] for x in p["obs"] if x[1] <= hloc]
                if o:
                    subidas.append(p["maxi"] - max(o))
            if len(subidas) < 15:
                continue
            for t in m["tramos"]:
                a, b = tramo(t["q"])
                if (a, b) in ya or not t["precios"]:
                    continue
                prob = sum(1 for s in subidas if a <= ms + s <= b) / len(subidas)
                if b < ms:
                    prob = 0.0
                i = bisect.bisect_right([x[0] for x in t["precios"]], t_dec.timestamp()) - 1
                if i < 0:
                    continue
                precio = t["precios"][i][1]
                if prob - precio >= margen and 0.03 <= precio <= 0.95:
                    coste = min(precio + DESLIZ, 0.99)
                    g = APUESTA / coste * t["gana"] - APUESTA * (1 + COMISION)
                    ops.append(dict(c=c, d=d, h=hloc, lado="SI", precio=precio, prob=prob, g=g)); ya.add((a, b))
                elif precio - prob >= margen and 0.05 <= precio <= 0.97:
                    coste = min(1 - precio + DESLIZ, 0.99)
                    g = APUESTA / coste * (not t["gana"]) - APUESTA * (1 + COMISION)
                    ops.append(dict(c=c, d=d, h=hloc, lado="NO", precio=precio, prob=prob, g=g)); ya.add((a, b))

    if not verbose:
        return ops
    informe("TOTAL", ops)
    for lado in ("SI", "NO"):
        informe(f"  lado {lado}", [o for o in ops if o["lado"] == lado])
    for h0, h1 in ((0, 9), (9, 12), (12, 15), (15, 18), (18, 24)):
        informe(f"  hora local {h0:02d}-{h1:02d}", [o for o in ops if h0 <= o["h"] < h1])
    for sem in sorted({datetime.fromisoformat(o["d"]).strftime("%G-W%V") for o in ops}):
        informe(f"  semana {sem}", [o for o in ops if datetime.fromisoformat(o["d"]).strftime("%G-W%V") == sem])
    porc = defaultdict(list)
    for o in ops: porc[o["c"]].append(o)
    print("Por ciudad:", ", ".join(f"{c} {sum(o['g'] for o in v):+.0f}" for c, v in sorted(porc.items(), key=lambda x: -sum(o['g'] for o in x[1]))))
    return ops


def informe(nombre, xs):
    if not xs:
        print(f"{nombre:28} sin operaciones"); return
    g = sum(x["g"] for x in xs)
    dias = defaultdict(float)
    for x in xs: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
    print(f"{nombre:28} ops {len(xs):5}  ganancia {g:+9.0f} $  por apuesta {g / len(xs) / APUESTA:+6.1%}  "
          f"aciertos {sum(x['g'] > 0 for x in xs) / len(xs):4.0%}  IC90 [{bs[50]:+.0f}, {bs[950]:+.0f}]")


if __name__ == "__main__":
    main()
