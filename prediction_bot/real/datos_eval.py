"""Datos para evaluar versiones del modelo: METAR (IEM) y GFS/ECMWF de los días recientes.

    python datos_eval.py DIR      → DIR/metar.json, DIR/nwp_rec.json
"""
import csv, io, json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bilberry"))
import nwp as N  # noqa: E402

EST = json.loads((Path(__file__).parent.parent / "sombra" / "estaciones.json").read_text())


def metar(dest, desde):
    out = {}
    fin = datetime.now(timezone.utc) + timedelta(days=1)
    for c, e in EST.items():
        r = N.pedir("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + "&".join(
            f"{k}={v}" for k, v in [("station", e["icao"]), ("data", "tmpf"), ("tz", "Etc/UTC"), ("format", "onlycomma"),
                                    ("missing", "empty"), ("report_type", "3"), ("report_type", "4"),
                                    ("year1", desde.year), ("month1", desde.month), ("day1", desde.day),
                                    ("year2", fin.year), ("month2", fin.month), ("day2", fin.day)]))
        if r:
            out[c] = [(x["valid"], float(x["tmpf"])) for x in csv.DictReader(io.StringIO(r.text)) if x.get("tmpf")]
    (dest / "metar.json").write_text(json.dumps(out))
    print("metar", len(out))


def nwp(dest, desde):
    path = dest / "nwp_rec.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    fin = ahora - timedelta(hours=ahora.hour % 6 + 6)
    run = datetime(desde.year, desde.month, desde.day, tzinfo=timezone.utc)
    with ThreadPoolExecutor(16) as p:
        while run <= fin:
            for modelo, fn, pasos in (("gfs", N.gfs_paso, N.PASOS_GFS), ("ecmwf", N.ecm_paso, N.PASOS_ECM)):
                k = f"{modelo}|{run:%Y-%m-%dT%H}"
                if k in out:
                    continue
                res = list(p.map(lambda s: fn(run, s, EST), pasos))
                if sum(x is not None for x in res) >= len(pasos) * 0.8:
                    out[k] = {"pasos": [s for s, x in zip(pasos, res) if x], "pub": max(x["pub"] for x in res if x),
                              "t": {c: [x["t"][c] for x in res if x] for c in EST}}
            run += timedelta(hours=6)
    path.write_text(json.dumps(out))
    print("nwp", len(out))


if __name__ == "__main__":
    d = Path(sys.argv[1])
    metar(d, datetime(2026, 8, 15))
    nwp(d, datetime(2026, 10, 26))
