"""Memecoins de Solana con máximo histórico desde el 1-ago-2026 y subida >= 100x desde su mínimo (CoinGecko),
nacidas desde el 15-jul-2026 (primera transacción del mint, Helius)."""
import json, os, time, urllib.request as U
K = os.environ["HELIUS_API_KEY"]
def get(u, h={"User-Agent": "Mozilla/5.0"}):
    for i in range(5):
        try: return json.load(U.urlopen(U.Request(u, headers=h), timeout=40))
        except Exception: time.sleep(15 * (i + 1))
lista = {x["id"]: x.get("platforms", {}).get("solana") for x in get("https://api.coingecko.com/api/v3/coins/list?include_platform=true") if x.get("platforms", {}).get("solana")}
out = {}
for pag in range(1, 5):
    for c in get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=solana-meme-coins&per_page=250&page={pag}") or []:
        m = lista.get(c["id"])
        if not m or not c.get("ath_date") or c["ath_date"] < "2026-08-01" or not c.get("atl") or c["ath"] / c["atl"] < 100: continue
        out[m] = {"nombre": c["symbol"], "ath": c["ath"], "ath_fecha": c["ath_date"][:10], "x": round(c["ath"] / c["atl"]),
                  "mc_ath": round(c["ath"] * (c.get("circulating_supply") or 0))}
    time.sleep(8)
for m in list(out):
    d = get(f"https://api.helius.xyz/v0/addresses/{m}/transactions?api-key={K}&limit=1&sort-order=asc")
    t = d[0]["timestamp"] if d else 0
    if t < 1784073600: out.pop(m); continue        # nacido antes del 15-jul-2026
    out[m]["nacio"] = t
json.dump(out, open("tokens.json", "w"), indent=1)
print(len(out)); [print(v["nombre"], v["x"], "x", v["mc_ath"], v["ath_fecha"], time.strftime("%F", time.gmtime(v["nacio"]))) for v in sorted(out.values(), key=lambda v: -v["mc_ath"])]
