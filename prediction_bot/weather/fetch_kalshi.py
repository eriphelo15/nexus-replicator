"""Descarga mercados de temperatura máxima de Kalshi ya resueltos y sus velas horarias.

Guarda todo en data/ (caché: se puede relanzar y continúa donde lo dejó).
    python fetch_kalshi.py --desde 2025-10-01
"""
import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

K = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ["KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN", "KXHIGHLAX", "KXHIGHPHIL"]
DATA = Path(__file__).parent / "data"
_last = [0.0]
_lock = threading.Lock()


def get(path, params=None, rps=8.0):
    for intento in range(8):
        with _lock:  # límite global de peticiones por segundo, compartido entre hilos
            espera = 1 / rps - (time.time() - _last[0])
            if espera > 0:
                time.sleep(espera)
            _last[0] = time.time()
        try:
            r = requests.get(K + path, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(2 ** intento)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** intento)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"demasiados reintentos: {path}")


def listar(path, params):
    out, cursor = [], None
    while True:
        p = dict(params, limit=1000)
        if cursor:
            p["cursor"] = cursor
        d = get(path, p)
        out += d.get("markets", [])
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            return out


def ts(iso):
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2025-10-01")
    args = ap.parse_args()
    (DATA / "candles").mkdir(parents=True, exist_ok=True)

    mercados = []
    if (DATA / "markets.json").exists():
        mercados = json.loads((DATA / "markets.json").read_text())
    for s in ([] if mercados else SERIES):
        hist = listar("/historical/markets", {"series_ticker": s})
        vivos = listar("/markets", {"series_ticker": s, "status": "settled"})
        for m in hist:
            m["_hist"] = True
        ms = {m["ticker"]: m for m in hist + vivos if m["close_time"] >= args.desde}
        print(s, "históricos", len(hist), "recientes", len(vivos), "en rango", len(ms), flush=True)
        mercados += ms.values()
    if not (DATA / "markets.json").exists():
        (DATA / "markets.json").write_text(json.dumps(mercados))

    pendientes = [m for m in mercados if not (DATA / "candles" / f"{m['ticker']}.json").exists()]
    print("velas pendientes:", len(pendientes), flush=True)
    # Lotes por evento: mismas fechas de apertura/cierre, pocas velas por petición.
    lotes = {}
    for m in pendientes:
        if not m.get("_hist"):
            lotes.setdefault(m["event_ticker"], []).append(m)
    print("eventos recientes:", len(lotes), flush=True)
    for lote in lotes.values():
        d = get("/markets/candlesticks", {
            "market_tickers": ",".join(m["ticker"] for m in lote),
            "start_ts": min(ts(m["open_time"]) for m in lote),
            "end_ts": max(ts(m["close_time"]) for m in lote),
            "period_interval": 60})
        for x in d.get("markets", []):
            (DATA / "candles" / f"{x.get('market_ticker') or x['ticker']}.json").write_text(json.dumps(x.get("candlesticks", [])))
    historicos = [m for m in pendientes if m.get("_hist")]

    def bajar(m):
        d = get(f"/historical/markets/{m['ticker']}/candlesticks", {
            "start_ts": ts(m["open_time"]), "end_ts": ts(m["close_time"]), "period_interval": 60})
        (DATA / "candles" / f"{m['ticker']}.json").write_text(json.dumps(d.get("candlesticks", [])))

    with ThreadPoolExecutor(8) as pool:
        for n, _ in enumerate(pool.map(bajar, historicos)):
            if n % 1000 == 0:
                print("históricas", n, "de", len(historicos), flush=True)
    print("listo", flush=True)


if __name__ == "__main__":
    main()
