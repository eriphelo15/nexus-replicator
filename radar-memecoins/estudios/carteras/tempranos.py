"""Compradores de las primeras 6 h de cada token ganador (API mejorada de Helius, orden ascendente)."""
import json, os, time, collections, urllib.request as U
K = os.environ["HELIUS_API_KEY"]; WSOL = "So11111111111111111111111111111111111111112"
def get(u):
    for i in range(6):
        try: return json.load(U.urlopen(u, timeout=60))
        except Exception: time.sleep(4 * (i + 1))
    return []
tokens = json.load(open("tokens.json")); compras = collections.defaultdict(dict)
for m, info in tokens.items():
    fin, desde, n = info["nacio"] + 6 * 3600, None, 0
    for _ in range(25):
        u = f"https://api.helius.xyz/v0/addresses/{m}/transactions?api-key={K}&limit=100&sort-order=asc" + (f"&after-signature={desde}" if desde else "")
        d = get(u)
        if not d: break
        for t in d:
            if t["timestamp"] > fin or t.get("transactionError"): continue
            sol = {a["account"]: a["nativeBalanceChange"] for a in t.get("accountData", [])}
            tok = collections.defaultdict(float); wsol = collections.defaultdict(float)
            for a in t.get("accountData", []):
                for b in a.get("tokenBalanceChanges", []):
                    q = int(b["rawTokenAmount"]["tokenAmount"]) / 10 ** b["rawTokenAmount"]["decimals"]
                    if b["mint"] == m: tok[b["userAccount"]] += q
                    elif b["mint"] == WSOL: wsol[b["userAccount"]] += q
            for w, q in tok.items():
                gasto = -(sol.get(w, 0) / 1e9 + wsol.get(w, 0))
                if q > 0 and gasto > 0.05 and m not in compras[w]:
                    compras[w][m] = {"t": t["timestamp"] - info["nacio"], "sol": round(gasto, 3)}
        n += len(d); desde = d[-1]["signature"]
        if d[-1]["timestamp"] > fin or len(d) < 100: break
    print(info["nombre"], n, "tx", flush=True)
json.dump(compras, open("tempranos.json", "w"))
rep = sorted(((len(v), w) for w, v in compras.items()), reverse=True)
print("carteras:", len(compras), "| en >=3 ganadores:", sum(1 for c, _ in rep if c >= 3), "| en >=2:", sum(1 for c, _ in rep if c >= 2))
for c, w in rep[:40]: print(c, w)
