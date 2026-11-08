"""Precio real del token 1, 3, 10 y 30 s después de cada operación suya (swaps de otros en la cadena).

Uso: python segundos.py -> segundos.jsonl (reanudable). Solo los tokens de seleccion.json.
El precio de cada swap es dólares/tokens del firmante (SOL convertido con el precio horario).
"""
import json, os, time, bisect, urllib.request as U
RPC="https://api.mainnet-beta.solana.com"; W="AH75Bn6QHSt5K2Ad4p1otns3JTwpSJWZTwiwKWNhmnKx"
WSOL="So11111111111111111111111111111111111111112"; EST={"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}
RETRASOS=(1,3,10,30)
def rpc(m,p):
    for i in range(8):
        try:
            r=json.load(U.urlopen(U.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"Content-Type":"application/json"}),timeout=40))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5*(i+1))
solh=sorted((v[0],v[4]) for v in json.load(open("sol.json"))); st=[a for a,_ in solh]
psol=lambda t: solh[max(bisect.bisect_right(st,t)-1,0)][1]
def precio_swap(sig, mint, t):
    tx=rpc("getTransaction",[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":1}])
    if not tx or tx["meta"]["err"]: return None
    m=tx["meta"]; keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]; f=keys[0]
    pre={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in m["preTokenBalances"] if b.get("owner")==f}
    post={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in m["postTokenBalances"] if b.get("owner")==f}
    dt=post.get(mint,0)-pre.get(mint,0)
    if abs(dt)<=0: return None
    q=(m["postBalances"][0]-m["preBalances"][0])/1e9+post.get(WSOL,0)-pre.get(WSOL,0)
    usd=q*psol(t)+sum(post.get(e,0)-pre.get(e,0) for e in EST)
    if usd==0 or (usd>0)==(dt>0): return None   # no es un swap del token contra SOL/USDC
    return abs(usd)/abs(dt)
sel=set(json.load(open("seleccion.json")))
ops=[json.loads(l) for l in open("operaciones.jsonl") if json.loads(l)["mint"] in sel]
mias=sorted(json.load(open("sigs30.json")),key=lambda s:s["blockTime"])
hechas={json.loads(l)["sig"] for l in open("segundos.jsonl")} if os.path.exists("segundos.jsonl") else set()
out=open("segundos.jsonl","a")
for n,o in enumerate(ops):
    if o["sig"] in hechas: continue
    # ancla: su siguiente transacción (o la más reciente) para listar las del token hacia atrás
    i=next((k for k,s in enumerate(mias) if s["blockTime"]>o["t"]+40),None)
    antes=mias[i]["signature"] if i is not None else None
    lista=[]; 
    for _ in range(6):
        p={"limit":1000,"until":o["sig"]}
        if antes: p["before"]=antes
        r=rpc("getSignaturesForAddress",[o["mint"],p])
        if not r: break
        lista+=r; antes=r[-1]["signature"]
        if len(r)<1000: break
    lista=sorted([s for s in lista if s.get("blockTime") and not s.get("err") and o["t"]<=s["blockTime"]<=o["t"]+40],key=lambda s:(s["blockTime"],s.get("slot",0)))
    fila={"sig":o["sig"],"mint":o["mint"],"t":o["t"],"lado":"compra" if o["cantidad"]>0 else "venta"}
    for d in RETRASOS:
        p=None
        for s in [s for s in lista if s["blockTime"]>=o["t"]+d][:4]:
            p=precio_swap(s["signature"],o["mint"],s["blockTime"])
            if p: break
        fila[f"p{d}"]=p
    out.write(json.dumps(fila)+"\n"); out.flush()
    if n%25==0: print(n,len(ops),flush=True)
print("fin",flush=True)
