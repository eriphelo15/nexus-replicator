"""Prueba combinada con previsiones FRESCAS: en cada hora se usa la última ejecución de GFS y de ECMWF
que ya estaba publicada (hora real del archivo en AWS), igual que haría un bot en tiempo real.
Solo máximas (los mínimos no tienen liquidez real). Reutiliza la lógica de combinado.py.

    python frescas.py [margen] [deslizamiento]
"""
import bisect, json, math, sys
from datetime import datetime, timezone

import numpy as np

import combinado as cb

class CiudadFresca(cb.Ciudad):
    """Usa, en cada momento, la última ejecución de GFS y de ECMWF ya publicada (hora real del archivo)."""

    def __init__(self, e, metar, prev, nwp, nombre):
        super().__init__(e, metar, prev)
        self.series = {}
        for k, d in nwp.items():
            modelo, run = k.split("|")
            t0 = datetime.fromisoformat(run).replace(tzinfo=timezone.utc).timestamp()
            vals = d["t"].get(nombre)
            if not vals:
                continue
            horas = np.array(d["pasos"], float)
            v = np.array(vals, float)
            if e["f"]:
                v = v * 1.8 + 32
            todas = np.arange(0, horas[-1] + 1)
            self.series.setdefault(modelo, []).append((d["pub"], t0, np.interp(todas, horas, v)))
        for m in self.series:
            self.series[m].sort()
        self.pubs = {m: [x[0] for x in l] for m, l in self.series.items()}

    def prevision(self, t, a, b, signo):
        por_modelo = []
        for m, lista in self.series.items():
            i = bisect.bisect_right(self.pubs[m], t) - 1
            if i < 0:
                return None
            _, t0, vals = lista[i]
            k0 = int((math.ceil(max(a, t) / cb.H) * cb.H - t0) // cb.H)
            k1 = int((b - t0) // cb.H)
            if k0 < 0 or k1 > len(vals) or k0 >= k1:
                return None
            por_modelo.append(float(np.max(signo * vals[k0:k1])))
        return float(np.mean(por_modelo)) if len(por_modelo) == 2 else None


def main():
    margen = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    est = json.loads((cb.DATA / "estaciones.json").read_text())
    metar = json.loads((cb.DATA / "metar.json").read_text())
    prev = json.loads((cb.DATA / "prev_horarias.json").read_text())
    nwp = json.loads((cb.DATA / "nwp.json").read_text())
    ciudades = {c: CiudadFresca(est[c], metar[c], prev[c], nwp, c) for c in est if c in metar and c in prev}
    inicio = min(k.split("|")[1] for k in nwp)[:10]
    mercados = [m for m in json.loads((cb.DATA / "mercados50.json").read_text())
                if m["tipo"] == "highest" and m["ciudad"] in ciudades and m["dia"] > inicio]
    mercados.sort(key=lambda m: m["dia"])
    print(f"{len(nwp)} ejecuciones desde {inicio}, {len(mercados)} mercados")
    for ventas in (False, True):
        ops = cb.simular(ciudades, mercados, margen=margen, ventas=ventas)
        print(f"\n=== FRESCAS margen {margen:.2f} desliz {cb.DESLIZ:.2f} {'CON ventas' if ventas else 'sin ventas'} ===")
        cb.informe("TOTAL", ops)
        for k, f in [("lado SI", lambda o: o["lado"] == "SI"), ("lado NO", lambda o: o["lado"] == "NO"),
                     ("durante el día (≤24 h)", lambda o: o["fase"] <= 24), ("víspera (24-36 h)", lambda o: 24 < o["fase"] <= 36),
                     ("antes (>36 h)", lambda o: o["fase"] > 36), ("precio < 20 c", lambda o: o["precio"] < 0.2),
                     ("precio 20-60 c", lambda o: 0.2 <= o["precio"] < 0.6), ("precio ≥ 60 c", lambda o: o["precio"] >= 0.6)]:
            cb.informe("  " + k, [o for o in ops if f(o)])
        json.dump(ops, open(cb.DATA / f"ops_frescas_{'ventas' if ventas else 'hold'}.json", "w"))


if __name__ == "__main__":
    main()
