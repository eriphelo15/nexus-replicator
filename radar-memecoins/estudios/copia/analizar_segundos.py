"""Copia con retraso de 1, 3, 10 y 30 s usando los precios reales de segundos.jsonl."""
import json, bisect, statistics as st, collections
solh=sorted((v[0],v[4]) for v in json.load(open("sol.json"))); stt=[a for a,_ in solh]
psol=lambda t: solh[max(bisect.bisect_right(stt,t)-1,0)][1]
ops={json.loads(l)["sig"]:json.loads(l) for l in open("operaciones.jsonl")}
usd=lambda o: abs(o.get("USDC",0)+o.get("USDT",0)+o.get("sol",0)*psol(o["t"]))
seg=[f for f in (json.loads(l) for l in open("segundos.jsonl")) if usd(ops[f["sig"]])>=1]
R=(1,3,10,30)
def ref(f): o=ops[f["sig"]]; return usd(o)/abs(o["cantidad"])
def precio(f,d):
    for k in [x for x in R if x>=d]:
        p=f.get(f"p{k}")
        if p and ref(f)>0 and 1/3<=p/ref(f)<=3: return p   # fuera de x3 es un swap mal leído
MED={}
print("operaciones medidas:",len(seg))
print("\nPeor precio que él (mediana; compras: más caro, ventas: más barato):")
for d in R:
    c=[precio(f,d)/(usd(ops[f["sig"]])/abs(ops[f["sig"]]["cantidad"]))-1 for f in seg if f["lado"]=="compra" and precio(f,d)]
    v=[(usd(ops[f["sig"]])/abs(ops[f["sig"]]["cantidad"]))/precio(f,d)-1 for f in seg if f["lado"]=="venta" and precio(f,d)]
    MED[(d,"compra")]=st.median(c); MED[(d,"venta")]=st.median(v)
    print(f"  {d:>2} s: compras {st.median(c):+.1%} (n={len(c)}) | ventas {st.median(v):+.1%} (n={len(v)})")
por=collections.defaultdict(list)
for f in sorted(seg,key=lambda f:f["t"]): por[f["mint"]].append(f)
velas={m:json.load(open(f"velas/{m}.json")) for m in por}
print("\nResultado en estos tokens (costes 1% por lado):")
for d in (0,)+R:
    suyo=nuestro=inv=0.0
    for m,lst in por.items():
        te=tn=0.0
        for f in lst:
            o=ops[f["sig"]]; u=usd(o); ps=u/abs(o["cantidad"])
            p=ps if d==0 else (precio(f,d) or ps*(1+MED[(d,f["lado"])]*(1 if f["lado"]=="compra" else -1)))
            if o["cantidad"]>0:
                inv+=u; suyo-=u; te+=o["cantidad"]; nuestro-=u*1.01; tn+=u/p
            else:
                fr=min(1,-o["cantidad"]/te) if te>0 else 0
                suyo+=u; te=max(0,te+o["cantidad"]); nuestro+=tn*fr*p*0.99; tn-=tn*fr
        ult=velas[m][-1][4] if velas[m] else 0
        if ult>10*max((usd(ops[f["sig"]])/abs(ops[f["sig"]]["cantidad"])) for f in lst): ult=0  # último precio absurdo
        suyo+=te*ult; nuestro+=tn*ult
    et="él (referencia)" if d==0 else f"copia a {d} s"
    print(f"  {et:16}: suyo ${suyo:,.0f} | copia ${nuestro:,.0f} ({nuestro/inv:+.1%} sobre ${inv:,.0f})" if d else f"  {et:16}: ${suyo:,.0f} ({suyo/inv:+.1%}) | copia sin retraso pero con costes ${nuestro:,.0f}")
