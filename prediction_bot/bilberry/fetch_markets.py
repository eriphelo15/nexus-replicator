"""Descarga los mercados de temperatura máxima de Polymarket (1-sep → 19-oct-2026) para 15 ciudades,
con su resultado y el historial de precios de cada tramo.  python fetch_markets.py"""
import json, re, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
import requests

CIUDADES = ["atlanta", "moscow", "los-angeles", "chicago", "warsaw", "madrid", "munich", "seoul",
            "denver", "miami", "seattle", "tokyo", "paris", "london", "dallas"]
DESDE, HASTA = date(2026, 9, 1), date(2026, 10, 19)
OUT = Path(__file__).parent / "data"; OUT.mkdir(exist_ok=True)


def get(url, **kw):
    for i in range(4):
        try:
            r = requests.get(url, timeout=60, **kw)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def evento(args):
    ciudad, d = args
    slug = f"highest-temperature-in-{ciudad}-on-{d.strftime('%B').lower()}-{d.day}-{d.year}"
    e = get("https://gamma-api.polymarket.com/events", params={"slug": slug})
    if not e:
        return None
    e = e[0]
    tramos = []
    for m in e.get("markets", []):
        try:
            tok = json.loads(m["clobTokenIds"])[0]
            gana = float(json.loads(m["outcomePrices"])[0]) > 0.5
        except Exception:
            continue
        h = get("https://clob.polymarket.com/prices-history",
                params={"market": tok, "startTs": int(time.mktime((d - timedelta(days=4)).timetuple())),
                        "endTs": int(time.mktime((d + timedelta(days=1)).timetuple())), "fidelity": 10})
        tramos.append(dict(q=m["question"], gana=gana, precios=(h or {}).get("history", [])))
    return dict(ciudad=ciudad, dia=d.isoformat(), desc=e.get("description", "")[:1500], tramos=tramos)


tareas = [(c, DESDE + timedelta(days=i)) for c in CIUDADES for i in range((HASTA - DESDE).days + 1)]
with ThreadPoolExecutor(8) as p:
    res = [r for r in p.map(evento, tareas) if r]
json.dump(res, open(OUT / "mercados.json", "w"))
print(len(res), "eventos,", sum(len(r["tramos"]) for r in res), "tramos,",
      sum(1 for r in res for t in r["tramos"] if t["precios"]), "con precios")
