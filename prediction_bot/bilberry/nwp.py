"""Previsiones de temperatura a 2 m directamente de los archivos públicos de NOAA (GFS) y ECMWF (IFS) en AWS.

Para cada ejecución (00/06/12/18 UTC) y cada paso de previsión hasta 54 h se descarga SOLO el campo de
temperatura (petición por rango de bytes), se interpola en cada aeropuerto y se guarda junto con la hora
real de publicación del archivo (cabecera Last-Modified). Sin límites de peticiones.

    python nwp.py [dias]          → data/nwp.json   (reanudable)
"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import eccodes
import numpy as np
import requests

DATA = Path(__file__).parent / "data"
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
ECM = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
PASOS_GFS = list(range(0, 55))           # horario
PASOS_ECM = list(range(0, 55, 3))        # cada 3 h
S = requests.Session()


def pedir(url, rango=None):
    for i in range(8):
        try:
            r = S.get(url, timeout=60, headers={"Range": f"bytes={rango[0]}-{rango[1]}"} if rango else {})
            if r.status_code in (200, 206):
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def puntos(msg, est):
    """Interpolación bilineal en cada estación de un campo GRIB en malla regular lat/lon."""
    gid = eccodes.codes_new_from_message(msg)
    try:
        ni, nj = eccodes.codes_get(gid, "Ni"), eccodes.codes_get(gid, "Nj")
        la1, lo1 = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees"), eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
        di, dj = eccodes.codes_get(gid, "iDirectionIncrementInDegrees"), eccodes.codes_get(gid, "jDirectionIncrementInDegrees")
        v = eccodes.codes_get_values(gid).reshape(nj, ni) - 273.15
    finally:
        eccodes.codes_release(gid)
    out = {}
    for c, e in est.items():
        y = (la1 - e["lat"]) / dj
        x = ((e["lon"] - lo1) % 360) / di
        j0, i0 = int(np.floor(y)), int(np.floor(x)) % ni
        fy, fx = y - np.floor(y), x - np.floor(x)
        i1 = (i0 + 1) % ni
        t = (v[j0, i0] * (1 - fx) * (1 - fy) + v[j0, i1] * fx * (1 - fy) +
             v[j0 + 1, i0] * (1 - fx) * fy + v[j0 + 1, i1] * fx * fy)
        out[c] = round(float(t), 2)
    return out


def gfs_paso(run, paso, est):
    base = f"{GFS}/gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{paso:03d}"
    idx = pedir(base + ".idx")
    if not idx:
        return None
    lineas = idx.text.splitlines()
    for k, l in enumerate(lineas):
        if ":TMP:2 m above ground:" in l:
            ini = int(l.split(":")[1]); fin = int(lineas[k + 1].split(":")[1]) - 1
            g = pedir(base, (ini, fin))
            pub = parsedate_to_datetime(idx.headers["Last-Modified"]).timestamp()
            return dict(pub=pub, t=puntos(g.content, est)) if g else None
    return None


def ecm_paso(run, paso, est):
    flujo = "oper" if run.hour in (0, 12) else "scda"
    for f in (flujo, "oper"):
        base = f"{ECM}/{run:%Y%m%d}/{run:%H}z/ifs/0p25/{f}/{run:%Y%m%d%H}0000-{paso}h-{f}-fc"
        idx = pedir(base + ".index")
        if not idx:
            continue
        for l in idx.text.splitlines():
            d = json.loads(l)
            if d.get("param") == "2t":
                g = pedir(base + ".grib2", (d["_offset"], d["_offset"] + d["_length"] - 1))
                pub = parsedate_to_datetime(idx.headers["Last-Modified"]).timestamp()
                return dict(pub=pub, t=puntos(g.content, est)) if g else None
    return None


def main(dias=35):
    est = json.loads((DATA / "estaciones.json").read_text())
    path = DATA / "nwp.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    fin = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    fin -= timedelta(hours=fin.hour % 6 + 12)          # última ejecución seguro completa
    runs = [fin - timedelta(hours=6 * i) for i in range(dias * 4)]
    with ThreadPoolExecutor(16) as p:
        for run in runs:
            for modelo, fn, pasos in (("gfs", gfs_paso, PASOS_GFS), ("ecmwf", ecm_paso, PASOS_ECM)):
                k = f"{modelo}|{run:%Y-%m-%dT%H}"
                if k in out:
                    continue
                res = list(p.map(lambda s: fn(run, s, est), pasos))
                if sum(r is not None for r in res) < len(pasos) * 0.8:
                    print("incompleto", k, sum(r is not None for r in res)); continue
                out[k] = {"pasos": [s for s, r in zip(pasos, res) if r],
                          "pub": max(r["pub"] for r in res if r),
                          "t": {c: [r["t"][c] for r in res if r] for c in est}}
                print(k, "ok", datetime.fromtimestamp(out[k]["pub"], timezone.utc).strftime("%H:%M"), flush=True)
            path.write_text(json.dumps(out))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 35)
