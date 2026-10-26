"""Descarga de datos para el sistema de temperatura en Polymarket.

  python datos.py estaciones   # coordenadas y zona horaria de cada aeropuerto
  python datos.py metar        # observaciones horarias (archivo de Iowa State, IEM)
  python datos.py previsiones  # previsiones archivadas de Open-Meteo (varios modelos, 1 y 2 días antes)
  python datos.py mercados     # mercados de Polymarket (máxima y mínima) + historial de precios

Todo se guarda en data/ (ignorado por git).
"""
import csv, io, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"; DATA.mkdir(exist_ok=True)
DESDE, HASTA = date(2026, 9, 1), date(2026, 10, 25)

# Aeropuerto oficial de resolución de Polymarket (según la descripción de cada mercado).
ICAO = {
    "houston": "KHOU", "warsaw": "EPWA", "nyc": "KLGA", "miami": "KMIA", "san-francisco": "KSFO",
    "madrid": "LEMD", "jeddah": "OEJN", "tokyo": "RJTT", "panama-city": "MPMG", "beijing": "ZBAA",
    "seoul": "RKSI", "chongqing": "ZUCK", "manila": "RPLL", "wuhan": "ZHHH", "london": "EGLC",
    "buenos-aires": "SAEZ", "guangzhou": "ZGGG", "mexico-city": "MMMX", "busan": "RKPK", "denver": "KBKF",
    "shenzhen": "ZGSZ", "moscow": "UUWW", "paris": "LFPB", "los-angeles": "KLAX", "toronto": "CYYZ",
    "tel-aviv": "LLBG", "qingdao": "ZSQD", "chengdu": "ZUUU", "shanghai": "ZSPD", "ankara": "LTAC",
    "zhengzhou": "ZHCC", "lucknow": "VILK", "karachi": "OPKC", "kuala-lumpur": "WMKK", "amsterdam": "EHAM",
    "seattle": "KSEA", "atlanta": "KATL", "chicago": "KORD", "dallas": "KDAL", "cape-town": "FACT",
    "wellington": "NZWN", "munich": "EDDM", "taipei": "RCSS", "sao-paulo": "SBGR", "helsinki": "EFHK",
    "austin": "KAUS", "singapore": "WSSS", "istanbul": "LTFM", "milan": "LIMC",
}
FAHRENHEIT = {"houston", "nyc", "miami", "san-francisco", "denver", "los-angeles", "seattle", "atlanta",
              "chicago", "dallas", "austin"}
TZ = {"houston": "America/Chicago", "warsaw": "Europe/Warsaw", "nyc": "America/New_York", "miami": "America/New_York",
      "san-francisco": "America/Los_Angeles", "madrid": "Europe/Madrid", "jeddah": "Asia/Riyadh", "tokyo": "Asia/Tokyo",
      "panama-city": "America/Panama", "beijing": "Asia/Shanghai", "seoul": "Asia/Seoul", "chongqing": "Asia/Shanghai",
      "manila": "Asia/Manila", "wuhan": "Asia/Shanghai", "london": "Europe/London", "buenos-aires": "America/Argentina/Buenos_Aires",
      "guangzhou": "Asia/Shanghai", "mexico-city": "America/Mexico_City", "busan": "Asia/Seoul", "denver": "America/Denver",
      "shenzhen": "Asia/Shanghai", "moscow": "Europe/Moscow", "paris": "Europe/Paris", "los-angeles": "America/Los_Angeles",
      "toronto": "America/Toronto", "tel-aviv": "Asia/Jerusalem", "qingdao": "Asia/Shanghai", "chengdu": "Asia/Shanghai",
      "shanghai": "Asia/Shanghai", "ankara": "Europe/Istanbul", "zhengzhou": "Asia/Shanghai", "lucknow": "Asia/Kolkata",
      "karachi": "Asia/Karachi", "kuala-lumpur": "Asia/Kuala_Lumpur", "amsterdam": "Europe/Amsterdam",
      "seattle": "America/Los_Angeles", "atlanta": "America/New_York", "chicago": "America/Chicago", "dallas": "America/Chicago",
      "cape-town": "Africa/Johannesburg", "wellington": "Pacific/Auckland", "munich": "Europe/Berlin", "taipei": "Asia/Taipei",
      "sao-paulo": "America/Sao_Paulo", "helsinki": "Europe/Helsinki", "austin": "America/Chicago", "singapore": "Asia/Singapore",
      "istanbul": "Europe/Istanbul", "milan": "Europe/Rome"}
MODELOS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", "jma_seamless", "ukmo_seamless",
           "meteofrance_seamless"]
MESES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
         "november", "december"]


def get(url, intentos=5, **kw):
    for i in range(intentos):
        try:
            r = requests.get(url, timeout=120, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def estaciones():
    r = get("https://aviationweather.gov/api/data/stationinfo", params={"ids": ",".join(ICAO.values()), "format": "json"})
    info = {s["icaoId"]: s for s in r.json()}
    out = {}
    for c, icao in ICAO.items():
        s = info.get(icao)
        if not s:
            print("sin datos", c, icao); continue
        out[c] = dict(icao=icao, lat=s["lat"], lon=s["lon"], tz=TZ[c], f=c in FAHRENHEIT)
    (DATA / "estaciones.json").write_text(json.dumps(out, indent=1))
    print(len(out), "estaciones")


def metar():
    est = json.loads((DATA / "estaciones.json").read_text())
    d0, d1 = DESDE - timedelta(days=1), HASTA + timedelta(days=2)
    out = {}
    for c, e in est.items():
        r = get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params=[
            ("station", e["icao"]), ("data", "tmpf"), ("tz", "Etc/UTC"), ("format", "onlycomma"),
            ("missing", "empty"), ("report_type", "3"), ("report_type", "4"),
            ("year1", d0.year), ("month1", d0.month), ("day1", d0.day),
            ("year2", d1.year), ("month2", d1.month), ("day2", d1.day)])
        filas = [(x["valid"], float(x["tmpf"])) for x in csv.DictReader(io.StringIO(r.text)) if x.get("tmpf")]
        out[c] = filas
        print(c, len(filas))
    (DATA / "metar.json").write_text(json.dumps(out))


def previsiones():
    est = json.loads((DATA / "estaciones.json").read_text())
    path = DATA / "prev_horarias.json"
    out = json.loads(path.read_text()) if path.exists() else {}

    def una(c):
        e = est[c]
        r = get("https://previous-runs-api.open-meteo.com/v1/forecast", params={
            "latitude": e["lat"], "longitude": e["lon"], "timezone": "GMT", "models": ",".join(MODELOS),
            "hourly": "temperature_2m_previous_day1,temperature_2m_previous_day2",
            "temperature_unit": "fahrenheit" if e["f"] else "celsius",
            "start_date": (DESDE - timedelta(days=30)).isoformat(), "end_date": (HASTA + timedelta(days=1)).isoformat()})
        return c, (r.json()["hourly"] if r else None)
    with ThreadPoolExecutor(3) as p:
        for c, h in p.map(una, [c for c in est if c not in out]):
            if h:
                out[c] = h; print(c, "ok")
            else:
                print(c, "FALLO")
    path.write_text(json.dumps(out))


def mercados():
    est = json.loads((DATA / "estaciones.json").read_text())
    path = DATA / "mercados50.json"
    hechos = {(e["tipo"], e["ciudad"], e["dia"]) for e in json.loads(path.read_text())} if path.exists() else set()
    viejos = json.loads(path.read_text()) if path.exists() else []

    def evento(a):
        tipo, c, d = a
        slug = f"{tipo}-temperature-in-{c}-on-{MESES[d.month - 1]}-{d.day}-{d.year}"
        r = get("https://gamma-api.polymarket.com/events", intentos=3, params={"slug": slug})
        if not r or not r.json():
            return None
        e = r.json()[0]
        ini = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - 4 * 86400
        tramos = []
        for m in e.get("markets", []):
            try:
                tok = json.loads(m["clobTokenIds"])[0]
                gana = float(json.loads(m["outcomePrices"])[0]) > 0.5
            except Exception:
                continue
            h = get("https://clob.polymarket.com/prices-history", intentos=3, params={
                "market": tok, "startTs": ini, "endTs": ini + 6 * 86400, "fidelity": 10})
            tramos.append(dict(q=m["question"], gana=gana, cerrado=m.get("closed"),
                               precios=[(x["t"], x["p"]) for x in (h.json().get("history", []) if h else [])]))
        return dict(tipo=tipo, ciudad=c, dia=d.isoformat(), tramos=tramos)

    tareas = [(t, c, DESDE + timedelta(days=i)) for t in ("highest", "lowest") for c in est
              for i in range((HASTA - DESDE).days + 1)]
    tareas = [a for a in tareas if (a[0], a[1], a[2].isoformat()) not in hechos]
    nuevos = []
    with ThreadPoolExecutor(12) as p:
        for i, r in enumerate(p.map(evento, tareas)):
            if r:
                nuevos.append(r)
            if i % 500 == 0:
                print(i, "/", len(tareas), len(nuevos), "eventos", flush=True)
    path.write_text(json.dumps(viejos + nuevos))
    print(len(viejos) + len(nuevos), "eventos")


if __name__ == "__main__":
    {"estaciones": estaciones, "metar": metar, "previsiones": previsiones, "mercados": mercados}[sys.argv[1]]()
