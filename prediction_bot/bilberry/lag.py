"""¿El precio tarda en reaccionar a las actualizaciones del modelo?  python lag.py"""
import json
from collections import defaultdict
import numpy as np
import combinado as cb

reg = json.load(open(cb.DATA / "registro.json"))
ser = defaultdict(dict)          # (ciudad, día, tramo) → {fase: (p, precio, gana, F)}
for c, d, fase, p, q, g, lo, F in reg:
    ser[(c, d, lo)][fase] = (p, q, g, F)
filas = []
for k, s in ser.items():
    for fase, (p, q, g, F) in s.items():
        if fase + 1 not in s:
            continue
        p0, q0, _, F0 = s[fase + 1]                       # una hora antes
        fut = {h: s[fase - h][1] for h in (1, 3, 6) if fase - h in s}
        filas.append((fase, p - p0, q - q0, p - q, F - F0, q, g, fut.get(1), fut.get(3), fut.get(6)))
r = np.array([[np.nan if v is None else v for v in f] for f in filas], float)
fase, dp, dq, gap, dF, q, g, q1, q3, q6 = r.T
print("n =", len(r))
for umbral in (0.05, 0.10, 0.20):
    for signo, nombre in ((1, "modelo SUBE prob."), (-1, "modelo BAJA prob.")):
        m = signo * dp >= umbral
        if m.sum() < 30: continue
        mov0 = signo * dq[m]
        print(f"Δp {nombre} ≥{umbral:.2f}: n={m.sum():6}  precio ya movido esa hora {np.nanmean(mov0):+.3f}  "
              f"después +1h {np.nanmean(signo * (q1[m] - q[m])):+.3f}  +3h {np.nanmean(signo * (q3[m] - q[m])):+.3f}  "
              f"+6h {np.nanmean(signo * (q6[m] - q[m])):+.3f}  a resolución {np.nanmean(signo * (g[m] - q[m])):+.3f}")
print("\nSolo cuando cambia la previsión (|ΔF| ≥ 1 grado) y el precio aún no se ha movido (|Δprecio| < 0.02):")
for signo, nombre in ((1, "SUBE"), (-1, "BAJA")):
    m = (signo * dp >= 0.10) & (np.abs(dF) >= 1) & (np.abs(dq) < 0.02)
    print(f"  {nombre}: n={m.sum():5}  +1h {np.nanmean(signo * (q1[m] - q[m])):+.3f}  +3h {np.nanmean(signo * (q3[m] - q[m])):+.3f}  "
          f"resolución {np.nanmean(signo * (g[m] - q[m])):+.3f}")
