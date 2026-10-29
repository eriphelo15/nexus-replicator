"""Fuentes de datos del bot en sombra: METAR (aeropuertos), GFS/ECMWF (AWS) y Polymarket."""
import csv, io, json, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import requests

AQUI = Path(__file__).parent
EST = json.loads((AQUI / "estaciones.json").read_text())
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
ECM = "https://storage.googleapis.com/ecmwf-open-data"  # copia oficial en Google Cloud: mismo contenido y hora que AWS
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
PASOS = {"gfs": list(range(0, 55)), "ecmwf": list(range(0, 55, 3))}
MESES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
         "november", "december"]
S = requests.Session()


def pedir(url, rango=None, intentos=4, **kw):
    for i in range(intentos):
        try:
            h = {"Range": f"bytes={rango[0]}-{rango[1]}"} if rango else {}
            r = S.get(url, timeout=60, headers=h, **kw)
            if r.status_code in (200, 206):
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))   # 503 = S3 pide ir más despacio
    return None


# ---------------------------------------------------------------- METAR
def a_unidad_c(c, fah):
    return round(c * 1.8 + 32) if fah else round(c)


def metar_historico(dias=40):
    """Archivo de Iowa State (IEM): {ciudad: [[ts, valor_en_unidad_del_mercado], ...]}"""
    ini = datetime.now(timezone.utc) - timedelta(days=dias)
    fin = datetime.now(timezone.utc) + timedelta(days=1)
    out = {}
    for c, e in EST.items():
        r = pedir("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params=[
            ("station", e["icao"]), ("data", "tmpf"), ("tz", "Etc/UTC"), ("format", "onlycomma"),
            ("missing", "empty"), ("report_type", "3"), ("report_type", "4"),
            ("year1", ini.year), ("month1", ini.month), ("day1", ini.day),
            ("year2", fin.year), ("month2", fin.month), ("day2", fin.day)])
        if not r:
            continue
        filas = []
        for x in csv.DictReader(io.StringIO(r.text)):
            if x.get("tmpf"):
                ts = datetime.strptime(x["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
                f = float(x["tmpf"])
                filas.append([ts, round(f) if e["f"] else round((f - 32) / 1.8)])
        out[c] = filas
    return out


def metar_reciente(horas=6):
    """Últimas observaciones (aviationweather.gov, casi en tiempo real)."""
    ids = {e["icao"]: c for c, e in EST.items()}
    r = pedir("https://aviationweather.gov/api/data/metar",
              params={"ids": ",".join(ids), "format": "json", "hours": horas})
    out = {}
    for x in (r.json() if r else []):
        c = ids.get(x.get("icaoId"))
        if c and x.get("temp") is not None and x.get("obsTime"):
            out.setdefault(c, []).append([float(x["obsTime"]), a_unidad_c(float(x["temp"]), EST[c]["f"])])
    return out


def fusionar_metar(store, nuevos, dias=45):
    lim = time.time() - dias * 86400
    for c, filas in nuevos.items():
        d = {int(t): v for t, v in store.get(c, [])}
        for t, v in filas:
            d[int(t)] = v
        store[c] = sorted([t, v] for t, v in d.items() if t >= lim)
    return store


# ---------------------------------------------------------------- GFS / ECMWF
def _puntos(msg):
    import eccodes
    gid = eccodes.codes_new_from_message(msg)
    try:
        ni, nj = eccodes.codes_get(gid, "Ni"), eccodes.codes_get(gid, "Nj")
        la1, lo1 = eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees"), eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees")
        di, dj = eccodes.codes_get(gid, "iDirectionIncrementInDegrees"), eccodes.codes_get(gid, "jDirectionIncrementInDegrees")
        v = eccodes.codes_get_values(gid).reshape(nj, ni) - 273.15
    finally:
        eccodes.codes_release(gid)
    out = {}
    for c, e in EST.items():
        y, x = (la1 - e["lat"]) / dj, ((e["lon"] - lo1) % 360) / di
        j0, i0 = int(np.floor(y)), int(np.floor(x)) % ni
        fy, fx = y - np.floor(y), x - np.floor(x)
        i1 = (i0 + 1) % ni
        out[c] = round(float(v[j0, i0] * (1 - fx) * (1 - fy) + v[j0, i1] * fx * (1 - fy) +
                             v[j0 + 1, i0] * (1 - fx) * fy + v[j0 + 1, i1] * fx * fy), 2)
    return out


def _gfs(run, paso):
    base = f"{GFS}/gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{paso:03d}"
    idx = pedir(base + ".idx", intentos=5)
    if not idx:
        return None
    ls = idx.text.splitlines()
    for k, l in enumerate(ls):
        if ":TMP:2 m above ground:" in l:
            g = pedir(base, (int(l.split(":")[1]), int(ls[k + 1].split(":")[1]) - 1))
            return dict(pub=parsedate_to_datetime(idx.headers["Last-Modified"]).timestamp(), t=_puntos(g.content)) if g else None
    return None


def _ecm(run, paso):
    for f in ("oper", "scda"):
        base = f"{ECM}/{run:%Y%m%d}/{run:%H}z/ifs/0p25/{f}/{run:%Y%m%d%H}0000-{paso}h-{f}-fc"
        idx = pedir(base + ".index", intentos=5)
        if not idx:
            continue
        for l in idx.text.splitlines():
            d = json.loads(l)
            if d.get("param") == "2t":
                g = pedir(base + ".grib2", (d["_offset"], d["_offset"] + d["_length"] - 1))
                return dict(pub=parsedate_to_datetime(idx.headers["Last-Modified"]).timestamp(), t=_puntos(g.content)) if g else None
    return None


def _completa(modelo, run):
    if modelo == "gfs":
        return pedir(f"{GFS}/gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f054.idx", intentos=1) is not None
    return any(pedir(f"{ECM}/{run:%Y%m%d}/{run:%H}z/ifs/0p25/{f}/{run:%Y%m%d%H}0000-54h-{f}-fc.index", intentos=1)
               for f in ("oper", "scda"))


def actualizar_nwp(store, dias=35, log=print):
    """Descarga las ejecuciones que falten (solo completas). store: {"gfs|2026-10-27T06": {pasos, pub, t}}"""
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    ult = ahora - timedelta(hours=ahora.hour % 6)
    runs = [ult - timedelta(hours=6 * i) for i in range(dias * 4)]
    lim = (ult - timedelta(days=dias + 1)).strftime("%Y-%m-%dT%H")
    for k in [k for k in store if k.split("|")[1] < lim]:
        del store[k]
    nuevos = 0
    with ThreadPoolExecutor(6) as p:
        for run in runs:
            for modelo, fn in (("gfs", _gfs), ("ecmwf", _ecm)):
                k = f"{modelo}|{run:%Y-%m-%dT%H}"
                if k in store:
                    continue
                if not _completa(modelo, run):          # ¿ya está publicado el último paso?
                    continue
                res = list(p.map(lambda s: fn(run, s), PASOS[modelo]))
                if sum(r is not None for r in res) < len(PASOS[modelo]) * 0.9:
                    continue
                store[k] = {"pasos": [s for s, r in zip(PASOS[modelo], res) if r],
                            "pub": max(r["pub"] for r in res if r),
                            "t": {c: [r["t"][c] for r in res if r] for c in EST}}
                nuevos += 1
                log(f"nueva ejecución {k}")
    return nuevos


# ---------------------------------------------------------------- Polymarket
def evento(ciudad, fecha):
    slug = f"highest-temperature-in-{ciudad}-on-{MESES[fecha.month - 1]}-{fecha.day}-{fecha.year}"
    r = pedir(f"{GAMMA}/events", params={"slug": slug}, intentos=2)
    if not r or not r.json():
        return None
    e = r.json()[0]
    tramos = []
    for m in e.get("markets", []):
        try:
            tok = json.loads(m["clobTokenIds"])
            precios = json.loads(m.get("outcomePrices") or "[]")
        except Exception:
            continue
        tramos.append(dict(q=m["question"], si=tok[0], no=tok[1], cerrado=bool(m.get("closed")),
                           resultado=[float(x) for x in precios] if precios else None))
    return dict(slug=slug, tramos=tramos)


def libros(tokens):
    out = {}
    for i in range(0, len(tokens), 50):
        for _ in range(3):
            try:
                r = S.post(f"{CLOB}/books", json=[{"token_id": t} for t in tokens[i:i + 50]], timeout=60)
                for b in r.json():
                    out[b["asset_id"]] = b
                break
            except Exception:
                time.sleep(3)
    return out


def mejor(b, lado):
    """Mejor precio de compra (bids) o venta (asks) de un libro, y $ disponibles hasta +3 c."""
    if not b or not b.get(lado):
        return None, 0.0
    ps = [(float(x["price"]), float(x["size"])) for x in b[lado]]
    p = max(x[0] for x in ps) if lado == "bids" else min(x[0] for x in ps)
    dep = sum(pp * s for pp, s in ps if (pp <= p + 0.03 if lado == "asks" else pp >= p - 0.03))
    return p, dep
