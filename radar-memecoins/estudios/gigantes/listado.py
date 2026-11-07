"""Descarga el listado de memecoins de Solana de CoinGecko y sus contratos (mints).

Genera cg_solana_memes.json y cg_mints.json, que usan diario.py y ../backtest/bajar.py.
"""
import json, time, urllib.request
H={"User-Agent":"Mozilla/5.0","accept":"application/json"}
g=lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=60))
memes=[]
for p in range(1,20):
    d=g(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=solana-meme-coins&per_page=250&page={p}")
    if not d: break
    memes+=d; time.sleep(8)
json.dump(memes,open("cg_solana_memes.json","w"))
lista=g("https://api.coingecko.com/api/v3/coins/list?include_platform=true")
json.dump({x["id"]:x["platforms"].get("solana") for x in lista},open("cg_mints.json","w"))
print(len(memes),"memecoins")
