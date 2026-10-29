"""Regla "reaccionar al cambio" (Δp ≥ 0,20) mes a mes, con los registros de ampliar.py + el original (sep-oct).

    python analizar_hist.py
"""
import json, random
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"
APUESTA, COM = 25.0, 0.017


def operaciones(reg, umbral=0.20, desliz=0.02, filtro=None):
    ser = defaultdict(dict)
    for c, d, fase, p, q, g, lo, F in reg:
        ser[(c, d, lo)][fase] = (p, q, g)
    ops = []
    for (c, d, lo), s in ser.items():
        for fase in sorted(s, reverse=True):
            if fase + 1 not in s:
                continue
            p, q, g = s[fase]; dp = p - s[fase + 1][0]
            if abs(dp) < umbral or not (0.05 <= q <= 0.95):
                continue
            lado = 1 if dp > 0 else -1
            coste = (q if lado > 0 else 1 - q) + desliz
            pj = p if lado > 0 else 1 - p
            o = dict(c=c, d=d, fase=fase, coste=coste, dp=abs(dp), gap=pj - coste,
                     g=APUESTA / coste * (g if lado > 0 else 1 - g) - APUESTA * (1 + COM))
            if filtro is None or filtro(o):
                ops.append(o)
            break
    return ops


def linea(nombre, xs):
    if not xs:
        return f"{nombre:26} sin operaciones"
    g = sum(x["g"] for x in xs); dias = defaultdict(float)
    for x in xs: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
    return (f"{nombre:26} ops {len(xs):5}  {g:+8.0f} $  {g / len(xs) / APUESTA:+6.1%}/apuesta  "
            f"aciertos {sum(x['g'] > 0 for x in xs) / len(xs):4.0%}  IC90 [{bs[50]:+.0f},{bs[950]:+.0f}]  "
            f"días+ {sum(x > 0 for x in v)}/{len(v)}")


def main():
    regs = {}
    for p in sorted((DATA / "hist").glob("registro_*.json")):
        regs[p.stem[9:]] = json.loads(p.read_text())
    viejo = json.loads((DATA / "registro.json").read_text())        # sep-oct (simulación original)
    for r in viejo:
        regs.setdefault(r[1][:7], []).append(r)
    filtro_barato = lambda o: o["coste"] >= 0.5 or (o["dp"] >= 0.3 and o["gap"] >= 0.35 and o["fase"] <= 12)
    for desliz in (0.02, 0.03):
        print(f"\n=== Regla Δp ≥ 0,20, deslizamiento {desliz:.2f} ===")
        tot, tot_f = [], []
        for mes in sorted(regs):
            ops = operaciones(regs[mes], desliz=desliz)
            opf = operaciones(regs[mes], desliz=desliz, filtro=filtro_barato)
            tot += ops; tot_f += opf
            print(linea(mes, ops))
        print(linea("TOTAL", tot))
        print(linea("TOTAL con filtro baratos", tot_f))
        est = {"invierno (dic-feb)": ("12", "01", "02"), "primavera (mar-may)": ("03", "04", "05"),
               "verano (jun-ago)": ("06", "07", "08"), "otoño (sep-oct)": ("09", "10")}
        for n, ms in est.items():
            print(linea(n, [o for o in tot if o["d"][5:7] in ms]))
        for n, a, b in (("precio < 0,30", 0, .3), ("precio 0,30-0,60", .3, .6), ("precio 0,60-0,85", .6, .85), ("precio ≥ 0,85", .85, 2)):
            print(linea(n, [o for o in tot if a <= o["coste"] < b]))


if __name__ == "__main__":
    main()
