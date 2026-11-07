import json, os, time, urllib.request
H={"User-Agent":"Mozilla/5.0","accept":"application/json"}
d=json.load(open('cg_solana_memes.json'))
sel=[]
for x in d:
    p=x['current_price']; mc=x['market_cap'] or x['fully_diluted_valuation'] or 0
    if not p or not x['ath'] or not mc: continue
    athmc=mc*x['ath']/p
    if athmc>=5e6 and x['ath_date']>='2025-10-01': sel.append(x['id'])
ids=['solana']+sel
print(len(ids),flush=True)
for i in ids:
    f=f'cg/{i}.json'
    if os.path.exists(f): continue
    for k in range(4):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(f'https://api.coingecko.com/api/v3/coins/{i}/market_chart?vs_currency=usd&days=365',headers=H),timeout=30))
            json.dump(r,open(f,'w')); break
        except Exception as e:
            print(i,e,flush=True); time.sleep(30*(k+1))
    time.sleep(7)
print('fin',flush=True)
