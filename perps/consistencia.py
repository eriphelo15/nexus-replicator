"""Consistencia de cada candidato con su historial de ganancias de Hyperliquid (endpoint portfolio)."""
import json, time, urllib.request as U, os
cands=json.load(open("candidatos1.json"))
hechos={json.loads(l)["dir"] for l in open("consistencia.jsonl")} if os.path.exists("consistencia.jsonl") else set()
out=open("consistencia.jsonl","a")
def post(body):
    for i in range(5):
        try:
            return json.load(U.urlopen(U.Request("https://api.hyperliquid.xyz/info",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=30))
        except Exception: time.sleep(3*(i+1))
for c in cands:
    if c["dir"] in hechos: continue
    p=post({"type":"portfolio","user":c["dir"]}) or []
    d=dict(p) if isinstance(p,list) else {}
    h=(d.get("allTime") or {})
    pnl=[(t/1000,float(v)) for t,v in h.get("pnlHistory",[])]; av=[(t/1000,float(v)) for t,v in h.get("accountValueHistory",[])]
    if len(pnl)<10: continue
    dias=(pnl[-1][0]-pnl[0][0])/86400
    # meses: pnl acumulado al final de cada 30 días
    meses=[]; t0=pnl[0][0]; ult=pnl[0][1]; k=1
    for t,v in pnl:
        if t>=t0+30*86400*k: meses.append(v-ult); ult=v; k+=1
    meses.append(pnl[-1][1]-ult)
    # peor caída del pnl acumulado, relativa al valor de la cuenta en el pico
    import statistics
    vals=[v for _,v in av if v>100]
    base=statistics.median(vals) if vals else 1.0
    pico=-1e18; peor_usd=0.0
    for t,v in pnl:
        pico=max(pico,v); peor_usd=max(peor_usd,pico-v)
    peor=peor_usd/max(base,1.0)
    r={**c,"dias":round(dias),"meses":len(meses),"meses_pos":sum(m>0 for m in meses),"peor_caida":round(peor,3),"peor_caida_usd":round(peor_usd),"capital_mediano":round(base),
       "pnl_hist":pnl[-1][1]}
    out.write(json.dumps(r)+"\n"); out.flush(); time.sleep(0.6)
print("fin")
