"""Estrategia "reaccionar al cambio": cada hora, si la probabilidad de nuestro modelo para un tramo cambia
≥ UMBRAL respecto a la hora anterior, comprar en esa dirección (SÍ si sube, NO si baja).
Coste: precio + DESLIZ, comisión 1,7 % en cada compra/venta. Salida: resolución o a las N horas.

    python cambio.py
"""
import json, random
from collections import defaultdict
import numpy as np
import combinado as cb

APUESTA, COM = 25.0, 0.017
reg = json.load(open(cb.DATA / "registro.json"))
ser = defaultdict(dict)
for c, d, fase, p, q, g, lo, F in reg:
    ser[(c, d, lo)][fase] = (p, q, g)


def correr(umbral, desliz, salida=None, pmin=0.05, pmax=0.95, fase_max=60, fase_min=0):
    ops = []
    for (c, d, lo), s in ser.items():
        dentro = False
        for fase in sorted(s, reverse=True):
            if dentro or fase + 1 not in s or not (fase_min < fase <= fase_max):
                continue
            p, q, g = s[fase]; p0, q0, _ = s[fase + 1]
            dp = p - p0
            if abs(dp) < umbral or not (pmin <= q <= pmax):
                continue
            lado = 1 if dp > 0 else -1
            coste = (q if lado > 0 else 1 - q) + desliz
            acc = APUESTA / coste
            if salida and fase - salida in s:
                qs = s[fase - salida][1]
                valor = (qs if lado > 0 else 1 - qs) - desliz
                cobro = acc * max(valor, 0) * (1 - COM)
            else:
                cobro = acc * (g if lado > 0 else 1 - g)
            ops.append(dict(c=c, d=d, fase=fase, lado=lado, q=q, g=cobro - APUESTA * (1 + COM)))
            dentro = True                         # una entrada por tramo y día
    return ops


def informe(nombre, xs):
    if not xs:
        print(f"{nombre:44} -"); return
    g = sum(x["g"] for x in xs); dias = defaultdict(float)
    for x in xs: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
    sem = defaultdict(float)
    import datetime as dt
    for x in xs: sem[dt.date.fromisoformat(x["d"]).strftime("%V")] += x["g"]
    print(f"{nombre:44} ops {len(xs):5}  {g:+7.0f} $  {g / len(xs) / APUESTA:+6.1%}/apuesta  IC90 [{bs[50]:+.0f},{bs[950]:+.0f}]  "
          f"semanas+ {sum(v > 0 for v in sem.values())}/{len(sem)}  {g / len(dias):+.0f} $/día")


if __name__ == "__main__":
    for desliz in (0.02, 0.03):
        print(f"\n--- deslizamiento {desliz:.2f} ---")
        for u in (0.10, 0.15, 0.20, 0.30):
            informe(f"Δp≥{u:.2f} hasta resolución", correr(u, desliz))
            informe(f"Δp≥{u:.2f} salida a 6 h", correr(u, desliz, salida=6))
        informe("Δp≥0.20 resolución, solo ≤24 h", correr(0.20, desliz, fase_max=24))
        informe("Δp≥0.20 resolución, solo >24 h", correr(0.20, desliz, fase_min=24))
