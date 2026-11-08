"""Simula copiar sus operaciones de Solana con retraso, usando velas de 1 min de GeckoTerminal.

Uso: python simular.py  (lee operaciones.jsonl; descarga velas en velas/ y precio de SOL)
Para cada token: sus compras en USD se copian con el mismo importe, al precio de la vela de 1 min
siguiente (retraso de 0-60 s, pesimista); cada venta suya vende la misma fracción de nuestra
posición, también en la vela siguiente. Lo que siga abierto se valora al último precio.
"""
import json, os, time, bisect, collections, urllib.request as U, urllib.error
G="https://api.geckoterminal.com/api/v2/networks/solana"; H={"User-Agent":"Mozilla/5.0"}
def g(u):
    for i in range(5):
        try: return json.load(U.urlopen(U.Request(u,headers=H),timeout=30))
        except urllib.error.HTTPError as e:
            if e.code==404: return {}
            time.sleep(12*(i+1))
        except Exception: time.sleep(4)
    return {}
ops=[json.loads(l) for l in open("operaciones.jsonl")]
ops.sort(key=lambda o:o["t"])
os.makedirs("velas",exist_ok=True)
# Precio de SOL por hora (pool SOL/USDC de Raydium)
if not os.path.exists("sol.json"):
    d=g(f"{G}/pools/Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE/ohlcv/hour?aggregate=1&limit=1000&currency=usd")
    json.dump(d["data"]["attributes"]["ohlcv_list"],open("sol.json","w"))
solh=sorted((v[0],v[4]) for v in json.load(open("sol.json")))
def precio_sol(t):
    i=bisect.bisect_right([a for a,_ in solh],t)-1; return solh[max(i,0)][1]
def usd(o):  # valor en dólares de la operación (positivo)
    return abs(o.get("USDC",0)+o.get("USDT",0)+o.get("sol",0)*precio_sol(o["t"]))
por=collections.defaultdict(list)
for o in ops:
    if usd(o)>=1: por[o["mint"]].append(o)
def velas(mint, t0, t1):
    f=f"velas/{mint}.json"
    if os.path.exists(f): return json.load(open(f))
    tp=((g(f"{G}/tokens/{mint}?include=top_pools").get("data") or {}).get("relationships") or {}).get("top_pools",{}).get("data") or []
    out=[]
    if tp:
        pool=tp[0]["id"].split("_",1)[1]; fin=t1+3600
        for _ in range(4):
            d=g(f"{G}/pools/{pool}/ohlcv/minute?aggregate=1&limit=1000&currency=usd&token=base&before_timestamp={int(fin)}")
            l=(d.get("data") or {}).get("attributes",{}).get("ohlcv_list") or []
            out+=l; time.sleep(2.2)
            if not l or min(v[0] for v in l)<=t0-60: break
            fin=min(v[0] for v in l)
    out=sorted({v[0]:v for v in out}.values()); json.dump(out,open(f,"w")); time.sleep(2.2); return out
res=[]
for mint,lst in por.items():
    v=velas(mint,lst[0]["t"],lst[-1]["t"])
    if len(v)<5: continue
    ts=[x[0] for x in v]
    def p_despues(t):
        i=bisect.bisect_right(ts,t)   # primera vela que empieza después de su operación
        return v[i][1] if i<len(v) else None
    suyo=nuestro=0.0; tok_el=tok_no=0.0; inv=0.0; ok=True
    for o in lst:
        u=usd(o); p=p_despues(o["t"])
        if o["cantidad"]>0:
            inv+=u; suyo-=u; tok_el+=o["cantidad"]
            if p: nuestro-=u; tok_no+=u/p
        else:
            fr=min(1.0,-o["cantidad"]/tok_el) if tok_el>0 else 0
            suyo+=u; tok_el=max(0.0,tok_el+o["cantidad"])
            if p and tok_no>0: nuestro+=tok_no*fr*p; tok_no-=tok_no*fr
    ult=v[-1][4]
    suyo+=tok_el*ult; nuestro+=tok_no*ult
    res.append({"mint":mint,"ops":len(lst),"invertido":round(inv,2),"pnl_suyo":round(suyo,2),"pnl_copia_bruto":round(nuestro,2)})
json.dump(res,open("resultado.json","w"),indent=0)
inv=sum(r["invertido"] for r in res); s=sum(r["pnl_suyo"] for r in res); c=sum(r["pnl_copia_bruto"] for r in res)
print(f"tokens {len(res)} | operaciones {sum(r['ops'] for r in res)} | invertido ${inv:,.0f}")
print(f"su resultado: ${s:,.0f} ({s/inv:+.1%})")
for coste in (0.005,0.01,0.02):
    n=c-2*coste*inv
    print(f"copiándole 1 min tarde, costes {coste:.1%}/lado: ${n:,.0f} ({n/inv:+.1%})")
gan=sorted(res,key=lambda r:-r["pnl_suyo"])
print("tokens ganadores para él:",sum(r["pnl_suyo"]>0 for r in res),"| para la copia:",sum(r["pnl_copia_bruto"]>0 for r in res))
print("top 5 (suyo / copia):",[(r["mint"][:6],r["pnl_suyo"],r["pnl_copia_bruto"]) for r in gan[:5]])
