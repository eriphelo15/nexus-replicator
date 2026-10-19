"""¿Cuánto cobraría un participante nuevo? Estima la cuota de premio frente a la liquidez ya puesta.

Fórmula de puntuación de Polymarket (docs "liquidity rewards"):
  S = ((v - s) / v)^2 * tamaño, con v = spread máximo premiado (céntimos) y s = distancia al punto medio.
  Lado 1 = bids YES + asks NO;  lado 2 = asks YES + bids NO.
  Si el precio medio está entre 0,10 y 0,90, quien solo cotiza un lado puntúa 1/3; si no, hay que cotizar los dos.
"""
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

C = "https://clob.polymarket.com"
MIN_RATE = float(sys.argv[1]) if len(sys.argv) > 1 else 50
NUESTRAS = 500  # acciones por lado que pondríamos

mk = [m for m in json.load(open("rewards_markets.json")) if m["total_daily_rate"] >= MIN_RATE]


def info(m):
    try:
        d = requests.get(f"{C}/markets/{m['condition_id']}", timeout=30).json()
        toks = d.get("tokens") or []
        if len(toks) != 2 or not d.get("accepting_orders"):
            return None
        return dict(m, yes=toks[0]["token_id"], no=toks[1]["token_id"], q=d.get("question", ""),
                    end=d.get("end_date_iso"), tick=float(d.get("minimum_tick_size") or 0.01))
    except Exception:
        return None


with ThreadPoolExecutor(8) as p:
    mk = [x for x in p.map(info, mk) if x]

books = {}
toks = [t for m in mk for t in (m["yes"], m["no"])]
for i in range(0, len(toks), 50):
    for b in requests.post(f"{C}/books", json=[{"token_id": t} for t in toks[i:i + 50]], timeout=60).json():
        books[b["asset_id"]] = b

res = []
for m in mk:
    by, bn = books.get(m["yes"]), books.get(m["no"])
    if not by or not bn or not by["bids"] or not by["asks"]:
        continue
    bb = max(float(x["price"]) for x in by["bids"])
    ba = min(float(x["price"]) for x in by["asks"])
    mid = (bb + ba) / 2
    v = m["rewards_max_spread"] / 100  # céntimos → dólares
    minsz = m["rewards_min_size"]

    def score(levels, side_price):
        tot = 0.0
        for x in levels:
            p, s = float(x["price"]), float(x["size"])
            dist = abs(side_price(p) - mid)
            if s >= minsz and dist < v:
                tot += ((v - dist) / v) ** 2 * s
        return tot
    # precios del NO expresados en términos de YES: bid NO a q equivale a ask YES a 1-q
    q1 = score(by["bids"], lambda p: p) + score(bn["asks"], lambda p: 1 - p)
    q2 = score(by["asks"], lambda p: p) + score(bn["bids"], lambda p: 1 - p)
    total = min(q1, q2)
    # Nosotros: bid YES y bid NO a mitad del spread premiado del medio.
    d = v / 2
    nuestro = ((v - d) / v) ** 2 * NUESTRAS
    cuota = nuestro / (total + nuestro)
    capital = NUESTRAS * ((mid - d) + (1 - mid - d))
    diario = m["total_daily_rate"] * cuota
    res.append(dict(cid=m["condition_id"], q=m["q"][:60], rate=m["total_daily_rate"], mid=round(mid, 3), spread=round(ba - bb, 3),
                    v=v, total_score=round(total), cuota=cuota, capital=capital, diario=diario,
                    anual_pct=diario * 365 / capital, end=m["end"]))

res.sort(key=lambda r: -r["anual_pct"])
json.dump(res, open("competencia.json", "w"), indent=1)
print(f"mercados analizados: {len(res)} (premio >= {MIN_RATE}$/día)")
print(f"{'premio/día':>10} {'medio':>6} {'spread':>6} {'puntos ajenos':>13} {'nuestra cuota':>13} {'capital':>8} {'$/día':>7} {'anual':>7}  pregunta")
for r in res[:25]:
    print(f"{r['rate']:>10.0f} {r['mid']:>6} {r['spread']:>6} {r['total_score']:>13} {r['cuota']:>13.1%} "
          f"{r['capital']:>8.0f} {r['diario']:>7.2f} {r['anual_pct']:>7.0%}  {r['q']}")
an = [r["anual_pct"] for r in res]
print("\nrentabilidad anual estimada (solo premios, sin pérdidas por ejecución): mediana",
      f"{statistics.median(an):.0%}", "| percentil 75", f"{sorted(an)[int(.75 * len(an))]:.0%}")
top = res[:20]
print(f"Si cotizáramos en los 20 mejores: capital {sum(r['capital'] for r in top):.0f}$, "
      f"premio {sum(r['diario'] for r in top):.0f}$/día")
