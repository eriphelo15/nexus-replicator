"""Lee cada transacción de la cartera de Solana y extrae sus compras y ventas de tokens.

Uso: python operaciones.py sigs30.json  -> operaciones.jsonl (reanudable)
Una operación = el token que cambia en su cartera frente a SOL/USDC/USDT que cambia al revés.
"""
import json, os, sys, time, urllib.request as U
RPC="https://api.mainnet-beta.solana.com"; W="AH75Bn6QHSt5K2Ad4p1otns3JTwpSJWZTwiwKWNhmnKx"
WSOL="So11111111111111111111111111111111111111112"
ESTABLES={"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":"USDC","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB":"USDT"}
def rpc(m,p):
    for i in range(8):
        try:
            r=json.load(U.urlopen(U.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"Content-Type":"application/json"}),timeout=40))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5*(i+1))
hechas=set()
if os.path.exists("operaciones.jsonl"):
    hechas={json.loads(l)["sig"] for l in open("operaciones.jsonl")}
if os.path.exists("vistas.txt"): hechas|=set(open("vistas.txt").read().split())
sigs=[s for s in json.load(open(sys.argv[1])) if s["signature"] not in hechas]
out=open("operaciones.jsonl","a"); vistas=open("vistas.txt","a")
for n,s in enumerate(sigs):
    tx=rpc("getTransaction",[s["signature"],{"encoding":"jsonParsed","maxSupportedTransactionVersion":1}])
    vistas.write(s["signature"]+"\n")
    if not tx: continue
    m=tx["meta"]; keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    sol=(m["postBalances"][keys.index(W)]-m["preBalances"][keys.index(W)])/1e9 if W in keys else 0.0
    pre={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in m["preTokenBalances"] if b.get("owner")==W}
    post={b["mint"]:float(b["uiTokenAmount"]["uiAmount"] or 0) for b in m["postTokenBalances"] if b.get("owner")==W}
    d={k:post.get(k,0)-pre.get(k,0) for k in set(pre)|set(post)}
    sol+=d.pop(WSOL,0.0)
    est={ESTABLES[k]:v for k,v in d.items() if k in ESTABLES}
    toks={k:v for k,v in d.items() if k not in ESTABLES and abs(v)>0}
    if len(toks)!=1: continue
    mint,q=next(iter(toks.items()))
    out.write(json.dumps({"sig":s["signature"],"t":s["blockTime"],"mint":mint,"cantidad":q,"sol":sol,**est})+"\n"); out.flush()
    if n%200==0: print(n,len(sigs),flush=True)
    time.sleep(0.12)
print("fin",flush=True)
