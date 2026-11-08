"""Operativa real de los candidatos (fills de 90 días): nº de cierres, acierto, duración, concentración."""
import json, time, statistics as st, urllib.request as U, collections
def post(b):
    for i in range(5):
        try: return json.load(U.urlopen(U.Request("https://api.hyperliquid.xyz/info",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"}),timeout=30))
        except Exception: time.sleep(3*(i+1))
c=[x for x in json.load(open("candidatos2.json")) if x["rot_mes"]>=1 and x["roi_mes"]<10]
ahora=int(time.time()*1000); ini=ahora-90*86400*1000
res=[]
for x in c:
    fills=[]; t=ini
    for _ in range(15):
        f=post({"type":"userFillsByTime","user":x["dir"],"startTime":t,"endTime":ahora}) or []
        if not f: break
        fills+=f; t=max(z["time"] for z in f)+1
        if len(f)<2000: break
        time.sleep(0.5)
    if not fills: continue
    json.dump(fills,open(f"fills_{x['dir'][:10]}.json","w"))
    cierres=[float(z["closedPnl"])-float(z.get("fee",0)) for z in fills if z["dir"].startswith("Close") or "->" in z["dir"]]
    # duración: desde que la posición de una moneda sale de 0 hasta que vuelve a 0
    pos=collections.defaultdict(float); abre={}; dur=[]
    for z in sorted(fills,key=lambda z:z["time"]):
        k=z["coin"]; antes=float(z["startPosition"]); s=float(z["sz"])*(1 if z["side"]=="B" else -1); despues=antes+s
        if abs(antes)<1e-12 and abs(despues)>0: abre[k]=z["time"]
        if abs(despues)<1e-9*max(abs(antes),1) or (antes*despues<0):
            if k in abre: dur.append((z["time"]-abre.pop(k))/60000)
            if antes*despues<0: abre[k]=z["time"]
    pnl=sum(cierres); top=sorted(cierres,reverse=True)[:5]
    monedas=collections.Counter(z["coin"] for z in fills).most_common(4)
    res.append({**x,"fills":len(fills),"cierres":len(cierres),"acierto":sum(p>0 for p in cierres)/max(len(cierres),1),
                "pnl_90d":pnl,"top5_pct":sum(top)/pnl if pnl>0 else None,"dur_med_min":st.median(dur) if dur else None,
                "posiciones":len(dur),"monedas":monedas})
    print(f"{x['dir'][:10]} fills {len(fills):5} | posiciones {len(dur):4} | duración mediana {st.median(dur) if dur else 0:7.1f} min | acierto {res[-1]['acierto']:.0%} | pnl 90d ${pnl:>11,.0f} | top5 {res[-1]['top5_pct'] or 0:.0%} | {monedas}",flush=True)
    time.sleep(0.5)
json.dump(res,open("operativa.json","w"),indent=0)
