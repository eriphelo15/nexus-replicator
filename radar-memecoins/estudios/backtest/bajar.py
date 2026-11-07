"""Pool principal y velas de 1 h (últimas 1000 h) de las memecoins de Solana de CoinGecko.

Uso (desde estudios/backtest): python bajar.py  -> pools.json y velas/<mint>.json
Necesita ../gigantes/cg_mints.json y ../gigantes/cg_solana_memes.json (listado de CoinGecko).
"""
import json, os, time, urllib.error, urllib.request
G="https://api.geckoterminal.com/api/v2/networks/solana"; H={"User-Agent":"Mozilla/5.0"}
def g(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30))
        except urllib.error.HTTPError as e:
            if e.code==404: return {}
            time.sleep(15*(i+1))
        except Exception: time.sleep(5)
    return {}
base="../gigantes/"
mints=json.load(open(base+"cg_mints.json")); memes=json.load(open(base+"cg_solana_memes.json"))
lista=[mints[x["id"]] for x in memes if mints.get(x["id"])]
os.makedirs("velas",exist_ok=True)
pools={} if not os.path.exists("pools.json") else json.load(open("pools.json"))
pend=[m for m in lista if m not in pools]
for i in range(0,len(pend),30):
    d=g(f"{G}/tokens/multi/{','.join(pend[i:i+30])}?include=top_pools")
    for x in d.get("data",[]):
        tp=((x.get("relationships") or {}).get("top_pools") or {}).get("data") or []
        pools[x["attributes"]["address"]]=tp[0]["id"].split("_",1)[1] if tp else None
    for m in pend[i:i+30]: pools.setdefault(m,None)
    json.dump(pools,open("pools.json","w")); time.sleep(2.2)
print("pools",sum(1 for v in pools.values() if v),flush=True)
for m,p in pools.items():
    f=f"velas/{m}.json"
    if not p or os.path.exists(f): continue
    d=g(f"{G}/pools/{p}/ohlcv/hour?aggregate=1&limit=1000&currency=usd")
    json.dump((d.get("data") or {}).get("attributes",{}).get("ohlcv_list") or [],open(f,"w")); time.sleep(2.2)
print("fin",flush=True)
