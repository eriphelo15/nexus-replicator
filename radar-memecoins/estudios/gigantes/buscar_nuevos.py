# Gigantes del listado de CoinGecko con ATH reciente: busca en GeckoTerminal sus pools y fecha de nacimiento.
import json, time, urllib.request
H={"User-Agent":"Mozilla/5.0"}
G="https://api.geckoterminal.com/api/v2/networks/solana"
d=json.load(open('cg_solana_memes.json')); mints=json.load(open('cg_mints.json'))
ya={c['mint'] for c in json.load(open('gigantes.json'))}
out=[]
for x in d:
    p=x['current_price']; mc=x['market_cap'] or x['fully_diluted_valuation'] or 0
    if not p or not x['ath'] or not mc: continue
    if mc*x['ath']/p<1e7 or x['ath_date']<'2026-04-01': continue
    m=mints.get(x['id'])
    if not m or m in ya: continue
    pools=[]
    for pag in (1,2):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(f"{G}/tokens/{m}/pools?page={pag}&include=dex",headers=H),timeout=30))
        except Exception as e:
            print('err',x['symbol'],e,flush=True); time.sleep(20); break
        time.sleep(2.6)
        for p_ in r.get('data',[]):
            a=p_['attributes']
            pools.append([a['pool_created_at'],a['address'],p_['relationships']['dex']['data']['id'],float(a.get('reserve_in_usd') or 0)])
        if len(r.get('data',[]))<20: break
    if not pools: continue
    pools.sort()
    nac=pools[0][0]
    # pools principales: los 3 con más liquidez, más el primero
    top=sorted(pools,key=lambda q:-q[3])[:3]
    if pools[0] not in top: top=[pools[0]]+top[:2]
    top.sort()
    out.append({"mint":m,"simbolo":x['symbol'].upper(),"nacimiento":nac,"pools":[q[:3] for q in top],
                "ath_date":x['ath_date'],"cg_id":x['id']})
    print(x['symbol'],nac,len(pools),flush=True)
json.dump(out,open('nuevos_cand.json','w'))
print('total',len(out))
