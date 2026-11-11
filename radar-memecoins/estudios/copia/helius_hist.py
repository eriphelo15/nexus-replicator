"""Historial de transacciones interpretadas de una cartera (API Enhanced de Helius). Reanudable.

Uso: python helius_hist.py <cartera> <salida.jsonl>   (clave en HELIUS_API_KEY)
"""
import json, os, sys, time, urllib.request as U, urllib.error
W, OUT = sys.argv[1], sys.argv[2]
KEY = os.environ["HELIUS_API_KEY"]
antes = None
if os.path.exists(OUT):
    filas = [json.loads(l) for l in open(OUT)]
    if filas: antes = min(filas, key=lambda x: x["timestamp"])["signature"]
f = open(OUT, "a"); n = 0
while True:
    u = f"https://api.helius.xyz/v0/addresses/{W}/transactions?api-key={KEY}&limit=100" + (f"&before={antes}" if antes else "")
    for i in range(5):
        try: d = json.load(U.urlopen(u, timeout=60)); break
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(3 * (i + 1)); continue
            raise
    if not d: break
    for t in d: f.write(json.dumps(t) + "\n")
    n += len(d); antes = d[-1]["signature"]; f.flush()
    if len(d) < 100: break
print("transacciones:", n)
