"""Simula la regla del tuit en Polymarket (temperatura máxima, 15 ciudades, 1-sep → 19-oct-2026).

Previsión nueva = máxima del día D según la ejecución de ~1 día antes (previous_day1),
previsión vieja = la de ~2 días antes (previous_day2); media de GFS y ECMWF en el aeropuerto oficial,
corregida con el error medio de los días ANTERIORES (walk-forward).
Si |nueva − vieja| ≥ 0,5 °C, se compran 25 $ del tramo que contiene la previsión nueva, al último precio
conocido a las 23:00 locales del día D-1 (+1 céntimo de deslizamiento, 1,7 % de comisión),
solo si cuesta entre 5 y 60 céntimos.  python backtest.py
"""
import json, re, statistics, time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

DATA = Path(__file__).parent / "data"
#            lat, lon, zona horaria, °F?
EST = {"atlanta": (33.6407, -84.4277, "America/New_York", 1), "moscow": (55.5915, 37.2615, "Europe/Moscow", 0),
       "los-angeles": (33.9416, -118.4085, "America/Los_Angeles", 1), "chicago": (41.9742, -87.9073, "America/Chicago", 1),
       "warsaw": (52.1657, 20.9671, "Europe/Warsaw", 0), "madrid": (40.4983, -3.5676, "Europe/Madrid", 0),
       "munich": (48.3538, 11.7861, "Europe/Berlin", 0), "seoul": (37.4602, 126.4407, "Asia/Seoul", 0),
       "denver": (39.7017, -104.7517, "America/Denver", 1), "miami": (25.7959, -80.2870, "America/New_York", 1),
       "seattle": (47.4502, -122.3088, "America/Los_Angeles", 1), "tokyo": (35.5494, 139.7798, "Asia/Tokyo", 0),
       "paris": (48.9694, 2.4414, "Europe/Paris", 0), "london": (51.5048, 0.0495, "Europe/London", 0),
       "dallas": (32.8471, -96.8518, "America/Chicago", 1)}
APUESTA, DESLIZ, COMISION, UMBRAL_C = 25, 0.01, 0.017, 0.5


def previsiones():
    f = DATA / "previsiones.json"
    if f.exists():
        return json.loads(f.read_text())
    out = {}
    for c, (lat, lon, tz, fah) in EST.items():
        for i in range(4):
            try:
                r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast", timeout=180, params={
                    "latitude": lat, "longitude": lon, "timezone": tz, "models": "gfs_seamless,ecmwf_ifs025",
                    "hourly": "temperature_2m_previous_day1,temperature_2m_previous_day2",
                    "temperature_unit": "fahrenheit" if fah else "celsius",
                    "start_date": "2026-08-01", "end_date": "2026-10-19"}).json()
                break
            except Exception:
                time.sleep(5)
        h, dia = r["hourly"], defaultdict(lambda: defaultdict(list))
        for k, vals in h.items():
            if k == "time":
                continue
            lead = 1 if "day1" in k else 2
            for t, v in zip(h["time"], vals):
                if v is not None:
                    dia[t[:10]][(lead, k.split("day")[1])].append(v)
        out[c] = {d: {f"{lead}": statistics.mean(max(v) for (l, _), v in x.items() if l == lead)
                      for lead in (1, 2) if any(l == lead for l, _ in x)} for d, x in dia.items()}
        print(c, "ok")
    f.write_text(json.dumps(out))
    return out


def tramo(q):
    """(mín, máx) del tramo, en la unidad del mercado."""
    n = [int(x) for x in re.findall(r"(-?\d+)\s*-\s*(-?\d+)°|(-?\d+)°", q)[0] if x]
    if "or below" in q: return (-999, n[0])
    if "or higher" in q: return (n[0], 999)
    return (n[0], n[-1])


def main():
    prev, mercados = previsiones(), json.load(open(DATA / "mercados.json"))
    mercados.sort(key=lambda e: e["dia"])
    errores, ops, todas = defaultdict(list), [], []
    for e in mercados:
        c, d = e["ciudad"], e["dia"]
        lat, lon, tz, fah = EST[c]
        p = prev.get(c, {}).get(d, {})
        gan = [t for t in e["tramos"] if t["gana"]]
        if "1" not in p or "2" not in p or len(gan) != 1:
            continue
        lo, hi = tramo(gan[0]["q"])
        real = lo if hi == 999 else hi if lo == -999 else (lo + hi) / 2
        sesgo = statistics.mean(errores[c][-20:]) if len(errores[c]) >= 5 else 0
        nueva, vieja = p["1"] + sesgo, p["2"] + sesgo
        errores[c].append(real - p["1"])
        cambio = abs(nueva - vieja) / (1.8 if fah else 1)
        hora = datetime.fromisoformat(d).replace(hour=23, tzinfo=ZoneInfo(tz)) - timedelta(days=1)
        for t in e["tramos"]:
            a, b = tramo(t["q"])
            if not (a - 0.5 <= nueva < b + 0.5):
                continue
            ant = [x["p"] for x in t["precios"] if x["t"] <= hora.timestamp()]
            if not ant:
                continue
            precio = ant[-1] + DESLIZ
            g = APUESTA / precio * (1 if t["gana"] else 0) - APUESTA * (1 + COMISION)
            fila = dict(c=c, d=d, precio=precio, g=g, cambio=cambio)
            todas.append(fila)
            if cambio >= UMBRAL_C and 0.05 <= precio <= 0.60:
                ops.append(fila)

    def informe(nombre, xs):
        if not xs:
            print(nombre, "sin operaciones"); return
        g = sum(x["g"] for x in xs)
        porm = defaultdict(float)
        for x in xs: porm[x["d"][:7]] += x["g"]
        print(f"{nombre:42} ops {len(xs):4}  ganancia {g:+8.0f} $  por apuesta {g/len(xs):+6.2f} $ "
              f"({g/len(xs)/APUESTA:+.0%})  aciertos {sum(x['g']>0 for x in xs)/len(xs):.0%}  "
              + "  ".join(f"{m}: {v:+.0f}" for m, v in sorted(porm.items())))
    informe("Regla del tuit (cambio ≥0,5 °C, 5-60 c)", ops)
    informe("Sin exigir cambio (5-60 c)", [x for x in todas if 0.05 <= x["precio"] <= 0.60])
    informe("Cambio ≥1 °C (5-60 c)", [x for x in todas if x["cambio"] >= 1 and 0.05 <= x["precio"] <= 0.60])
    informe("Regla del tuit, solo 1-19 oct", [x for x in ops if x["d"] >= "2026-10-01"])
    # remuestreo por días para ver si la ganancia es distinguible de cero
    import random
    dias = defaultdict(float)
    for x in ops: dias[x["d"]] += x["g"]
    v = list(dias.values()); random.seed(1)
    bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(2000))
    print(f"Intervalo 90 % de la ganancia total (regla del tuit): {bs[100]:+.0f} $ a {bs[1900]:+.0f} $")


if __name__ == "__main__":
    main()
