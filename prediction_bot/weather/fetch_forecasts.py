"""Descarga previsiones archivadas (tal como se publicaron antes de cada día) de Open-Meteo.

previous_day1 / previous_day2 = valor previsto por la ejecución del modelo de 1 / 2 días antes.
Guarda la máxima diaria prevista por (ciudad, modelo, antelación) en data/forecasts.json.
"""
import json
import time
from pathlib import Path

import requests

DATA = Path(__file__).parent / "data"
# Estaciones oficiales del informe climatológico (CLI) de NWS que usa Kalshi.
# El día climatológico va en hora ESTÁNDAR local todo el año (sin horario de verano).
CITIES = {
    "KXHIGHNY":   (40.7790, -73.9692, "Etc/GMT+5"),   # Central Park
    "KXHIGHCHI":  (41.7842, -87.7553, "Etc/GMT+6"),   # Midway
    "KXHIGHMIA":  (25.7881, -80.3169, "Etc/GMT+5"),   # Miami Intl
    "KXHIGHAUS":  (30.3208, -97.7604, "Etc/GMT+6"),   # Camp Mabry
    "KXHIGHDEN":  (39.8466, -104.6562, "Etc/GMT+7"),  # Denver Intl
    "KXHIGHLAX":  (33.9382, -118.3866, "Etc/GMT+8"),  # LAX
    "KXHIGHPHIL": (39.8733, -75.2268, "Etc/GMT+5"),   # Philadelphia Intl
}
MODELS = ["ecmwf_ifs025", "gfs_seamless", "gem_seamless", "jma_seamless",
          "ukmo_seamless", "icon_seamless", "ncep_nbm_conus"]


def fetch(lat, lon, tz, model, start, end):
    url = "https://previous-runs-api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "models": model, "timezone": tz,
              "hourly": "temperature_2m_previous_day1,temperature_2m_previous_day2",
              "temperature_unit": "fahrenheit", "start_date": start, "end_date": end}
    for intento in range(4):
        try:
            r = requests.get(url, params=params, timeout=180)
            if r.status_code == 200:
                return r.json()
            print("  http", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("  error", e)
        time.sleep(5 * (intento + 1))
    return None


def main(start="2025-09-25", end="2026-10-06"):
    out_path = DATA / "forecasts.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    for city, (lat, lon, tz) in CITIES.items():
        for model in MODELS:
            key = f"{city}|{model}"
            if key in out:
                continue
            d = fetch(lat, lon, tz, model, start, end)
            if not d or "hourly" not in d:
                print(key, "SIN DATOS")
                continue
            h = d["hourly"]
            daily = {}
            for lead in (1, 2):
                col = next((c for c in h if f"previous_day{lead}" in c), None)
                if not col:
                    continue
                por_dia = {}
                for t, v in zip(h["time"], h[col]):
                    if v is not None:
                        por_dia.setdefault(t[:10], []).append(v)
                # Solo días completos (24 horas) para que la máxima sea válida.
                daily[str(lead)] = {dia: max(vs) for dia, vs in por_dia.items() if len(vs) == 24}
            out[key] = daily
            print(key, {k: len(v) for k, v in daily.items()}, flush=True)
            out_path.write_text(json.dumps(out))


if __name__ == "__main__":
    main()
