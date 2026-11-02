"""Previsión oficial NBM (EE. UU.) por aeropuerto: máxima diaria prevista (TXN) y su desviación (XND).

Boletín de texto NBS de cada ejecución (00/06/12/18 UTC) desde el bucket público de NOAA en AWS.
La máxima del día local D es el TXN válido a las 00 UTC del día D+1 (periodo diurno 12-00 UTC).

    python fetch_nbm.py DIR [desde AAAA-MM-DD]   → DIR/nbm.json (reanudable)
"""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

EST = json.loads((Path(__file__).parent.parent / "sombra" / "estaciones.json").read_text())
NBM = {c: e["icao"] for c, e in EST.items()
       if e["icao"] in {"KHOU", "KLGA", "KMIA", "KSFO", "KBKF", "KLAX", "KSEA", "KATL", "KORD", "KDAL", "KAUS", "CYYZ"}}
URL = "https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.{d:%Y%m%d}/{d:%H}/text/blend_nbstx.t{d:%H}z"


def descargar(run):
    for i in range(4):
        try:
            r = requests.get(URL.format(d=run), timeout=120)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    return None


def parsear(texto, run):
    out = {}
    lineas = texto.splitlines()
    idx = {l[1:5]: i for i, l in enumerate(lineas) if l.startswith(" ") and "NBS GUIDANCE" in l}
    for c, icao in NBM.items():
        i = idx.get(icao)
        if i is None:
            continue
        bloque = lineas[i:i + 26]
        utc = next((l for l in bloque if l.startswith(" UTC")), None)
        fhr = next((l for l in bloque if l.startswith(" FHR")), None)
        txn = next((l for l in bloque if l.startswith(" TXN")), None)
        xnd = next((l for l in bloque if l.startswith(" XND")), None)
        if not (utc and fhr and txn):
            continue
        # columnas de 3 caracteres a partir de la posición 5
        cols = [(m.start(), int(m.group())) for m in re.finditer(r"\d+", fhr[5:])]
        vals = []
        for pos, h in cols:
            seg = txn[5 + pos:5 + pos + 3].strip()
            sd = xnd[5 + pos:5 + pos + 3].strip() if xnd else ""
            if seg.lstrip("-").isdigit():
                valido = run + timedelta(hours=h)
                vals.append((valido.isoformat(), int(seg), int(sd) if sd.isdigit() else None))
        out[c] = vals
    return out


def main(dirp, desde):
    path = dirp / "nbm.json"
    datos = json.loads(path.read_text()) if path.exists() else {}
    ahora = datetime.now(timezone.utc) - timedelta(hours=3)
    runs, r = [], desde
    while r <= ahora:
        if r.strftime("%Y-%m-%dT%H") not in datos:
            runs.append(r)
        r += timedelta(hours=6)

    def una(run):
        resp = descargar(run)
        if not resp:
            return run, None
        return run, dict(pub=parsedate_to_datetime(resp.headers["Last-Modified"]).timestamp(), est=parsear(resp.text, run))
    with ThreadPoolExecutor(6) as p:
        for i, (run, x) in enumerate(p.map(una, runs)):
            if x:
                datos[run.strftime("%Y-%m-%dT%H")] = x
            if i % 20 == 0:
                print(run, len(datos), flush=True)
                path.write_text(json.dumps(datos))
    path.write_text(json.dumps(datos))
    print("ejecuciones NBM:", len(datos))


if __name__ == "__main__":
    d = Path(sys.argv[1])
    ini = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=timezone.utc) if len(sys.argv) > 2 else datetime(2026, 9, 1, tzinfo=timezone.utc)
    main(d, ini)
