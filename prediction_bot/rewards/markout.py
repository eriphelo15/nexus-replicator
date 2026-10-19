"""Coste oculto de dar liquidez: ¿cuánto pierde quien tiene la orden puesta cuando se la ejecutan?

Para cada operación real de los últimos días (lado del que la provoca = taker) calcula el resultado
del que tenía la orden puesta (maker), comparando el precio de la operación con el precio posterior:
  - a 1 hora vista
  - hasta ahora (precio medio actual)
Positivo = el maker gana (cobra el spread); negativo = le ejecutaron sabiendo más que él.
Luego compara, mercado a mercado, premio diario estimado vs. resultado de ejecución.
"""
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

D = "https://data-api.polymarket.com/trades"
DIAS = 7
now = time.time()
fin = lambda x: datetime.fromisoformat(x["end"].replace("Z", "+00:00"))
cands = [x for x in json.load(open("competencia.json"))
         if x.get("end") and fin(x) - datetime.now(timezone.utc) > timedelta(days=2) and 0.15 <= x["mid"] <= 0.85]


def trades(cid):
    out, off = [], 0
    while off < 3000:
        try:
            r = requests.get(D, params={"market": cid, "limit": 500, "offset": off, "takerOnly": "true"}, timeout=30)
            b = r.json()
        except Exception:
            break
        if not isinstance(b, list) or not b:
            break
        out += b
        if b[-1]["timestamp"] < now - DIAS * 86400 or len(b) < 500:
            break
        off += 500
    return [t for t in out if t["timestamp"] >= now - DIAS * 86400]


def analizar(x):
    ts = trades(x["cid"])
    if len(ts) < 5:
        return dict(x, n=len(ts), vol_dia=0, mk1h=None, mknow=None)
    # Todo en términos del YES. side = lado del taker.
    pts = []
    for t in ts:
        p = t["price"] if t["outcomeIndex"] == 0 else 1 - t["price"]
        buy_yes = (t["side"] == "BUY") == (t["outcomeIndex"] == 0)
        pts.append((t["timestamp"], p, t["size"], buy_yes))
    pts.sort()
    tiempos = [q[0] for q in pts]

    def precio_en(tq):
        # último precio negociado en o antes de tq; si tq es futuro, el medio actual
        if tq >= now:
            return x["mid"]
        import bisect
        i = bisect.bisect_right(tiempos, tq) - 1
        return pts[i][1] if i >= 0 else x["mid"]

    m1, mn, vol = 0.0, 0.0, 0.0
    for t0, p, s, buy_yes in pts:
        sgn = 1 if buy_yes else -1  # maker vendió YES si el taker compró
        m1 += sgn * (p - precio_en(t0 + 3600)) * s
        mn += sgn * (p - x["mid"]) * s
        vol += s
    dias = max((now - pts[0][0]) / 86400, 1)
    return dict(x, n=len(ts), vol_dia=vol / dias, mk1h=m1 / dias, mknow=mn / dias)


with ThreadPoolExecutor(8) as p:
    res = list(p.map(analizar, cands))
json.dump(res, open("markout.json", "w"), indent=1)

print(f"mercados: {len(res)}")
print(f"{'premio':>7} {'cuota':>6} {'premio nuestro':>14} {'vol/día':>8} {'maker 1h/día':>12} {'maker→ahora/día':>15} {'neto/día (cuota)':>16}  pregunta")
for x in sorted(res, key=lambda x: -x["diario"])[:30]:
    if x["mknow"] is None:
        neto = x["diario"]
        print(f"{x['rate']:>7.0f} {x['cuota']:>6.0%} {x['diario']:>14.1f} {x['vol_dia']:>8.0f} {'—':>12} {'—':>15} {neto:>16.1f}  {x['q'][:50]}")
        continue
    neto = x["diario"] + x["cuota"] * min(x["mk1h"], x["mknow"])
    print(f"{x['rate']:>7.0f} {x['cuota']:>6.0%} {x['diario']:>14.1f} {x['vol_dia']:>8.0f} {x['mk1h']:>12.1f} {x['mknow']:>15.1f} {neto:>16.1f}  {x['q'][:50]}")
con = [x for x in res if x["mknow"] is not None]
print("\nmercados con operaciones:", len(con), "| sin operaciones en 7 días:", len(res) - len(con))
print("resultado medio del maker por día y mercado: 1h", round(statistics.fmean(x["mk1h"] for x in con), 2),
      "| hasta ahora", round(statistics.fmean(x["mknow"] for x in con), 2))
