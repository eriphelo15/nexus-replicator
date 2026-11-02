"""Simulación con PRECIOS REALES del libro de órdenes (registro horario del bot en sombra).

Entrada: registro.jsonl.gz (cada hora: prob. del modelo, punto medio, precio de compra SÍ y NO) +
resoluciones.json. Cada compra se hace al precio real de venta del libro (ask) + 1,7 % de comisión.

    python sim_real.py DIR_DATOS
"""
import gzip, json, random, sys
from collections import defaultdict
from pathlib import Path

APUESTA, COM = 25.0, 0.017


def cargar(dirp):
    res = json.loads((dirp / "resoluciones.json").read_text())
    filas = []
    for l in gzip.open(dirp / "registro.jsonl.gz", "rt"):
        r = json.loads(l)
        g = res.get(f"{r['c']}|{r['d']}", {}).get(str(r["lo"]))
        if g is None or r["medio"] is None:
            continue
        r["gana"] = g
        filas.append(r)
    return filas


def simular(filas, decide):
    """decide(fila) → "SI" / "NO" / None. Una entrada por tramo y día (la primera)."""
    hechas, ops = set(), []
    for r in sorted(filas, key=lambda x: x["t"]):
        k = (r["c"], r["d"], r["lo"])
        if k in hechas:
            continue
        lado = decide(r)
        if not lado:
            continue
        precio = r["ask"] if lado == "SI" else r["ask_no"]
        if precio is None or precio >= 0.995:
            continue
        gana = r["gana"] if lado == "SI" else not r["gana"]
        ops.append(dict(d=r["d"], fase=r["fase"], precio=precio, g=APUESTA / precio * gana - APUESTA * (1 + COM)))
        hechas.add(k)
    return ops


def linea(nombre, xs):
    if not xs:
        return f"{nombre:44} sin operaciones"
    g = sum(x["g"] for x in xs); dias = defaultdict(float)
    for x in xs: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
    return (f"{nombre:44} ops {len(xs):4}  {g:+7.0f} $  {g / len(xs) / APUESTA:+6.1%}/apuesta  "
            f"IC90 [{bs[50]:+.0f},{bs[950]:+.0f}]  días+ {sum(x > 0 for x in v)}/{len(v)}")


if __name__ == "__main__":
    d = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    F = cargar(d)
    print(len(F), "filas con resultado")
    # validación: la regla del bot (Δp ≥ 0,20, precio medio 0,05-0,95, mercado "vivo")
    regla = lambda r: (("SI" if r["dp"] > 0 else "NO") if r["dp"] is not None and abs(r["dp"]) >= 0.2 and r["vivo"]
                       and 0.05 <= r["medio"] <= 0.95 else None)
    print(linea("VALIDACIÓN regla del bot (Δp≥0,20)", simular(F, regla)))
    # calibración: ¿quién acierta más, el modelo o el punto medio del mercado?
    vivos = [r for r in F if r["vivo"]]
    bm = sum((r["p"] - r["gana"]) ** 2 for r in vivos) / len(vivos)
    bq = sum((r["medio"] - r["gana"]) ** 2 for r in vivos) / len(vivos)
    print(f"Brier modelo {bm:.4f}  mercado {bq:.4f}  (n={len(vivos)})")
    # estrategia "brecha": comprar cuando la prob. del modelo supera al precio REAL de compra en ≥ m
    for m in (0.05, 0.10, 0.15, 0.20):
        def brecha(r, m=m):
            if not r["vivo"]:
                return None
            if r["ask"] is not None and r["p"] - r["ask"] >= m:
                return "SI"
            if r["ask_no"] is not None and (1 - r["p"]) - r["ask_no"] >= m:
                return "NO"
            return None
        ops = simular(F, brecha)
        print(linea(f"brecha ≥ {m:.2f}", ops))
        for n, a, b in (("  faltan ≤12 h", 0, 12), ("  12-24 h", 12, 24), ("  24-36 h", 24, 36), ("  >36 h", 36, 99)):
            print(linea(n, [o for o in ops if a < o["fase"] <= b]))
