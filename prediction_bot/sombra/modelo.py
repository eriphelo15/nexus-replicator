"""Modelo de probabilidad (idéntico al de la simulación: bilberry/combinado.py + frescas.py).

Máxima del día = max(máxima ya medida, previsión de las horas que quedan + error histórico).
Previsión = media de la última ejecución publicada de GFS y de ECMWF en el aeropuerto.
Error histórico = residuos de los 30 días anteriores a la misma hora relativa (walk-forward).
"""
import bisect, math, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

H = 3600
VENTANA, MIN_POOL, SUAVIZADO = 30, 12, 0.6
_erf = np.frompyfunc(math.erf, 1, 1)


def phi(x):
    return 0.5 * (1 + _erf(np.asarray(x, float) / math.sqrt(2)).astype(float))


def tramo(q):
    n = [int(x) for g in re.findall(r"(-?\d+)\s*-\s*(-?\d+)\s*°|(-?\d+)\s*°", q) for x in g if x]
    if "or below" in q: return (-999, n[0])
    if "or higher" in q or "or above" in q: return (n[0], 999)
    return (n[0], n[-1])


class Ciudad:
    def __init__(self, e, metar, nwp, nombre):
        self.tz, self.f = ZoneInfo(e["tz"]), e["f"]
        self.obs = sorted((float(t), v) for t, v in metar)
        self.obs_t = [x[0] for x in self.obs]
        self.series = {}
        for k, d in nwp.items():
            modelo, run = k.split("|")
            vals = d["t"].get(nombre)
            if not vals:
                continue
            t0 = datetime.fromisoformat(run).replace(tzinfo=timezone.utc).timestamp()
            horas, v = np.array(d["pasos"], float), np.array(vals, float)
            if self.f:
                v = v * 1.8 + 32
            self.series.setdefault(modelo, []).append((d["pub"], t0, np.interp(np.arange(0, horas[-1] + 1), horas, v)))
        for m in self.series:
            self.series[m].sort(key=lambda x: x[0])
        self.pubs = {m: [x[0] for x in l] for m, l in self.series.items()}
        self._res = {}

    def dia(self, d):
        ini = datetime.fromisoformat(d).replace(tzinfo=self.tz)
        return ini.astimezone(timezone.utc).timestamp(), (ini + timedelta(days=1)).astimezone(timezone.utc).timestamp()

    def obs_entre(self, a, b):
        i, j = bisect.bisect_left(self.obs_t, a), bisect.bisect_left(self.obs_t, b)
        return [x[1] for x in self.obs[i:j]]

    def prevision(self, t, a, b):
        por = []
        for m, lista in self.series.items():
            i = bisect.bisect_right(self.pubs[m], t) - 1
            if i < 0:
                return None
            _, t0, vals = lista[i]
            k0 = int((math.ceil(max(a, t) / H) * H - t0) // H)
            k1 = int((b - t0) // H)
            if k0 < 0 or k1 > len(vals) or k0 >= k1:
                return None
            por.append(float(np.max(vals[k0:k1])))
        return float(np.mean(por)) if len(por) == 2 else None

    def residuos_dia(self, d):
        """Error de la previsión ese día para cada fase (como en la simulación). Cacheado."""
        if d in self._res:
            return self._res[d]
        a, b = self.dia(d)
        out = {}
        if len(self.obs_entre(a, b)) >= 18:
            for fase in range(1, 61):
                t = ((b - fase * H + 600 - H) // H) * H + 600
                resto = self.obs_entre(max(a, t - 300), b)
                f = self.prevision(t, a, b)
                if f is not None and resto:
                    out[fase] = max(resto) - f
        self._res[d] = out
        return out

    def fase(self, d, t):
        """Fase (horas que faltan, como en la simulación) correspondiente a la decisión de las hh:10."""
        a, b = self.dia(d)
        for f in range(1, 61):
            if ((b - f * H) // H) * H + 600 == t:
                return f
        return None

    def probabilidades(self, d, t, tramos):
        """{(lo, hi): prob} para el día d en el instante t (hh:10 UTC), o None si no hay datos suficientes."""
        a, b = self.dia(d)
        fase = self.fase(d, t)
        if fase is None or t >= b:
            return None, None
        f = self.prevision(t, a, b)
        limite = (datetime.fromisoformat(d) - timedelta(days=1)).date().isoformat()
        dias = sorted({datetime.fromtimestamp(x, self.tz).date().isoformat() for x in self.obs_t})
        res = [self.residuos_dia(dd)[fase] for dd in dias if dd < limite and fase in self.residuos_dia(dd)][-VENTANA:]
        if f is None or len(res) < MIN_POOL:
            return fase, None
        vistos = self.obs_entre(a, t - 300)
        ya = max(vistos) if vistos else -1e9
        centros = f + np.array(res)
        out = {}
        for lo0, hi0 in tramos:
            lo, hi = lo0 - 0.5, hi0 + 0.5
            cdf_hi = phi((hi - centros) / SUAVIZADO) if hi < 900 else np.ones_like(centros)
            cdf_lo = phi((lo - centros) / SUAVIZADO) if lo > -900 else np.zeros_like(centros)
            if ya >= hi:
                p = 0.0
            elif ya >= lo:
                p = float(np.mean(cdf_hi))
            else:
                p = float(np.mean(cdf_hi - cdf_lo))
            out[(lo0, hi0)] = p
        return fase, dict(prevision=f, ya=None if ya < -1e8 else ya, p=out)
