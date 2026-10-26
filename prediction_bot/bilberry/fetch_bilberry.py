"""Descarga todas las operaciones de Bilberry de los últimos N días (por ventanas de tiempo).
    python fetch_bilberry.py [dias]"""
import json, sys, time
from pathlib import Path
import requests

W = "0xbf13934a1fec7d3211fc15c138d84ac2a691b91a"
OUT = Path(__file__).parent / "data" / "bilberry_trades.jsonl"


def pagina(start, end, off):
    for i in range(5):
        try:
            r = requests.get("https://data-api.polymarket.com/activity", timeout=60, params={
                "user": W, "type": "TRADE", "start": start, "end": end, "limit": 500, "offset": off,
                "sortBy": "TIMESTAMP", "sortDirection": "ASC"})
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"fallo {start}-{end}-{off}")


def main(dias=40):
    fin = int(time.time()); ini = fin - dias * 86400
    vistos, n = set(), 0
    with open(OUT, "w") as fh:
        t = ini
        while t < fin:
            paso = 6 * 3600
            off = 0
            while True:
                b = pagina(t, t + paso, off)
                for x in b:
                    k = (x["transactionHash"], x["asset"], x["side"], x["size"])
                    if k not in vistos:
                        vistos.add(k); fh.write(json.dumps(x) + "\n"); n += 1
                if len(b) < 500:
                    break
                off += 500
                if off >= 3000:   # ventana demasiado llena: el API no pagina más allá
                    print("aviso: ventana saturada", t); break
            t += paso
    print(n, "operaciones")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
