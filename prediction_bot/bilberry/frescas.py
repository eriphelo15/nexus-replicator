"""Prueba combinada con previsiones FRESCAS: en cada hora se usa la última ejecución de GFS y de ECMWF
que ya estaba publicada (inicio + 5 h GFS, + 7 h ECMWF), igual que haría un bot en tiempo real.
Solo máximas (los mínimos no tienen liquidez real). Reutiliza la lógica de combinado.py.

    python frescas.py [margen] [deslizamiento]
"""
import json, math, sys
from datetime import datetime, timezone

import numpy as np

import combinado as cb

RETRASO = {"gfs_seamless": 5 * 3600, "ecmwf_ifs025": 7 * 3600}


class CiudadFresca(cb.Ciudad):
    def __init__(self, e, metar, prev, runs, nombre):
        super().__init__(e, metar, prev)
        self.series = {}   # modelo → lista ordenada de (disponible_desde, t0, valores)
        for k, porc in runs.items():
            d = porc.get(nombre)
            if not d:
                continue
            t0 = datetime.fromisoformat(d["t0"]).replace(tzinfo=timezone.utc).timestamp()
            for m, vals in d.items():
                if m == "t0" or not vals:
                    continue
                self.series.setdefault(m, []).append((t0 + RETRASO[m], t0, vals))
        for m in self.series:
            self.series[m].sort()

    def prevision(self, t, a, b, signo):
        por_modelo = []
        for m, lista in self.series.items():
            disp = [x for x in lista if x[0] <= t]
            if not disp:
                continue
            _, t0, vals = disp[-1]
            hs = []
            v = math.ceil(max(a, t) / cb.H) * cb.H
            while v < b:
                k = int((v - t0) // cb.H)
                if k < 0 or k >= len(vals) or vals[k] is None:
                    hs = None; break
                hs.append(signo * vals[k]); v += cb.H
            if hs:
                por_modelo.append(max(hs))
        return float(np.mean(por_modelo)) if len(por_modelo) == len(self.series) and por_modelo else None


def main():
    margen = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    est = json.loads((cb.DATA / "estaciones.json").read_text())
    metar = json.loads((cb.DATA / "metar.json").read_text())
    prev = json.loads((cb.DATA / "prev_horarias.json").read_text())
    ej = json.loads((cb.DATA / "ejecuciones.json").read_text())
    ciudades = {c: CiudadFresca(est[c], metar[c], prev[c], ej["runs"], c) for c in ej["ciudades"]}
    inicio = min(ej["runs"])[:10]
    mercados = [m for m in json.loads((cb.DATA / "mercados50.json").read_text())
                if m["tipo"] == "highest" and m["ciudad"] in ciudades and m["dia"] > inicio]
    mercados.sort(key=lambda m: m["dia"])
    print(f"{len(ej['runs'])} ejecuciones desde {inicio}, {len(mercados)} mercados")
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
