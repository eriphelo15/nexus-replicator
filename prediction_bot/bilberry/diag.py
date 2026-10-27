"""Calibración: ¿nuestras probabilidades aciertan más o menos que el precio del mercado?  python diag.py"""
import json, sys
from collections import defaultdict
import numpy as np
import combinado as cb, frescas as fr

est = json.loads((cb.DATA / "estaciones.json").read_text()); metar = json.loads((cb.DATA / "metar.json").read_text())
prev = json.loads((cb.DATA / "prev_horarias.json").read_text()); nwp = json.loads((cb.DATA / "nwp.json").read_text())
ciudades = {c: fr.CiudadFresca(est[c], metar[c], prev[c], nwp, c) for c in est if c in metar and c in prev}
mercados = sorted([m for m in json.loads((cb.DATA / "mercados50.json").read_text()) if m["tipo"] == "highest"
                   and m["ciudad"] in ciudades and m["dia"] > "2026-09-11"], key=lambda m: m["dia"])
reg = []
cb.simular(ciudades, mercados, margen=9, registro=reg)
json.dump(reg, open(cb.DATA / "registro.json", "w"))
r = np.array([(x[2], x[3], x[4], x[5]) for x in reg], float)
for nombre, msk in [("todo", r[:, 0] > 0), ("≤12 h", r[:, 0] <= 12), ("12-24 h", (r[:, 0] > 12) & (r[:, 0] <= 24)),
                    ("24-36 h", (r[:, 0] > 24) & (r[:, 0] <= 36)), (">36 h", r[:, 0] > 36)]:
    x = r[msk]
    bm, bq = np.mean((x[:, 1] - x[:, 3]) ** 2), np.mean((x[:, 2] - x[:, 3]) ** 2)
    mix = np.mean((0.5 * x[:, 1] + 0.5 * x[:, 2] - x[:, 3]) ** 2)
    print(f"{nombre:8} n={len(x):6}  Brier modelo {bm:.4f}  mercado {bq:.4f}  mezcla 50/50 {mix:.4f}")
print("\nCalibración del modelo (prob. prevista → frecuencia real):")
for lo, hi in [(0, .05), (.05, .15), (.15, .3), (.3, .5), (.5, .7), (.7, .9), (.9, 1.01)]:
    x = r[(r[:, 1] >= lo) & (r[:, 1] < hi)]
    y = r[(r[:, 2] >= lo) & (r[:, 2] < hi)]
    print(f"  {lo:.2f}-{hi:.2f}: modelo → {x[:, 3].mean():.3f} (n={len(x)})   mercado → {y[:, 3].mean():.3f} (n={len(y)})")
