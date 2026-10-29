"""Amplía la simulación de "reaccionar al cambio" a otros meses (por defecto dic-2025 → ago-2026).

  python ampliar.py metar      # observaciones de aeropuertos del periodo (IEM)
  python ampliar.py nwp        # ejecuciones GFS/ECMWF del periodo (AWS)
  python ampliar.py mercados   # mercados de máxima de Polymarket, un archivo por mes (data/hist/AAAA-MM.json)
  python ampliar.py simular    # registro de probabilidades y precios, mes a mes → data/hist/registro_AAAA-MM.json

Todo es reanudable. Los slugs antiguos no llevan año ("...-on-january-15"); se comprueba la fecha real.
"""
import csv, io, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
HIST = DATA / "hist"; HIST.mkdir(parents=True, exist_ok=True)
DESDE, HASTA = date(2025, 12, 1), date(2026, 8, 31)
EST = json.loads((DATA / "estaciones.json").read_text())
MESES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
         "november", "december"]


def get(url, intentos=4, **kw):
    for i in range(intentos):
        try:
            r = requests.get(url, timeout=90, **kw)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    return None


def metar():
    path = HIST / "metar.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    d0, d1 = DESDE - timedelta(days=45), HASTA + timedelta(days=2)
    for c, e in EST.items():
        if c in out:
            continue
        r = get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params=[
            ("station", e["icao"]), ("data", "tmpf"), ("tz", "Etc/UTC"), ("format", "onlycomma"),
            ("missing", "empty"), ("report_type", "3"), ("report_type", "4"),
            ("year1", d0.year), ("month1", d0.month), ("day1", d0.day),
            ("year2", d1.year), ("month2", d1.month), ("day2", d1.day)])
        if not r:
            print("fallo", c); continue
        out[c] = [(x["valid"], float(x["tmpf"])) for x in csv.DictReader(io.StringIO(r.text)) if x.get("tmpf")]
        print(c, len(out[c]), flush=True)
        path.write_text(json.dumps(out))


def nwp():
    import nwp as N
    path = HIST / "nwp.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    ini = datetime(DESDE.year, DESDE.month, DESDE.day, tzinfo=timezone.utc) - timedelta(days=45)
    fin = datetime(HASTA.year, HASTA.month, HASTA.day, tzinfo=timezone.utc) + timedelta(days=1)
    runs, r = [], ini
    while r <= fin:
        runs.append(r); r += timedelta(hours=6)
    with ThreadPoolExecutor(16) as p:
        for i, run in enumerate(runs):
            for modelo, fn, pasos in (("gfs", N.gfs_paso, N.PASOS_GFS), ("ecmwf", N.ecm_paso, N.PASOS_ECM)):
                k = f"{modelo}|{run:%Y-%m-%dT%H}"
                if k in out:
                    continue
                res = list(p.map(lambda s: fn(run, s, EST), pasos))
                if sum(x is not None for x in res) < len(pasos) * 0.8:
                    print("incompleto", k, flush=True); continue
                out[k] = {"pasos": [s for s, x in zip(pasos, res) if x], "pub": max(x["pub"] for x in res if x),
                          "t": {c: [x["t"][c] for x in res if x] for c in EST}}
            if i % 20 == 0:
                print(run, len(out), flush=True)
                path.write_text(json.dumps(out))
    path.write_text(json.dumps(out))


def _evento(c, d):
    for slug in (f"highest-temperature-in-{c}-on-{MESES[d.month - 1]}-{d.day}-{d.year}",
                 f"highest-temperature-in-{c}-on-{MESES[d.month - 1]}-{d.day}"):
        r = get("https://gamma-api.polymarket.com/events", intentos=3, params={"slug": slug})
        if not r or not r.json():
            continue
        e = r.json()[0]
        fin = (e.get("endDate") or "")[:10]
        if fin and abs((date.fromisoformat(fin) - d).days) > 2:      # slug sin año de otro año
            continue
        ini = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - 3 * 86400
        tramos = []
        for m in e.get("markets", []):
            try:
                tok = json.loads(m["clobTokenIds"])[0]
                gana = float(json.loads(m["outcomePrices"])[0]) > 0.5
            except Exception:
                continue
            h = get("https://clob.polymarket.com/prices-history", intentos=3, params={
                "market": tok, "startTs": ini, "endTs": ini + 5 * 86400, "fidelity": 10})
            tramos.append(dict(q=m["question"], gana=gana, cerrado=m.get("closed"),
                               precios=[(x["t"], x["p"]) for x in (h.json().get("history", []) if h else [])]))
        return dict(tipo="highest", ciudad=c, dia=d.isoformat(), tramos=tramos)
    return None


def mercados():
    mes = date(DESDE.year, DESDE.month, 1)
    while mes <= HASTA:
        path = HIST / f"{mes:%Y-%m}.json"
        sig = date(mes.year + (mes.month == 12), mes.month % 12 + 1, 1)
        if not path.exists():
            dias = [mes + timedelta(days=i) for i in range((sig - mes).days)]
            with ThreadPoolExecutor(12) as p:
                res = [r for r in p.map(lambda a: _evento(*a), [(c, d) for c in EST for d in dias]) if r]
            path.write_text(json.dumps(res))
            print(f"{mes:%Y-%m}: {len(res)} eventos", flush=True)
        mes = sig


def simular():
    """Genera el registro (probabilidad del modelo y precio cada hora) para cada mes, con las mismas reglas."""
    import combinado as cb
    import frescas as fr
    from datetime import datetime as _dt
    est = EST
    metar_raw = json.loads((HIST / "metar.json").read_text())
    nwp_ = json.loads((HIST / "nwp.json").read_text())
    prev_dummy = {"time": ["2025-01-01T00:00"], **{f"temperature_2m_previous_day{l}_x": [None] for l in (1, 2)}}
    ciudades = {c: fr.CiudadFresca(est[c], metar_raw[c], prev_dummy, nwp_, c) for c in est if c in metar_raw}
    for path in sorted(HIST.glob("20??-??.json")):
        dest = HIST / f"registro_{path.stem}.json"
        if dest.exists():
            continue
        ms = sorted(json.loads(path.read_text()), key=lambda m: m["dia"])
        reg = []
        cb.simular(ciudades, ms, margen=9, registro=reg)
        dest.write_text(json.dumps(reg))
        print(path.stem, len(ms), "mercados", len(reg), "filas", flush=True)


if __name__ == "__main__":
    {"metar": metar, "nwp": nwp, "mercados": mercados, "simular": simular}[sys.argv[1]]()
