"""Para los compradores tempranos repetidos: filtra bots, baja historial desde el 1-ago (Helius) y calcula
PnL realizado por mes y una copia simulada ($100 por compra suya, tope $500 por token, 3% de deslizamiento
+ 1% de comisión por lado; misma fracción en las ventas)."""
import json, os, sys, time, calendar, bisect, collections, urllib.request as U
K = os.environ["HELIUS_API_KEY"]; WSOL = "So11111111111111111111111111111111111111112"
EST = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}
T0 = calendar.timegm((2026, 8, 1, 0, 0, 0)); MIN_GANADORES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
def get(u, data=None):
    for i in range(6):
        try:
            r = U.Request(u, data=json.dumps(data).encode() if data else None, headers={"Content-Type": "application/json"})
            return json.load(U.urlopen(r, timeout=60))
        except Exception: time.sleep(4 * (i + 1))
RPC = f"https://mainnet.helius-rpc.com/?api-key={K}"
c = get("https://api.hyperliquid.xyz/info", {"type": "candleSnapshot", "req": {"coin": "SOL", "interval": "1h", "startTime": T0 * 1000 - 86400000, "endTime": int(time.time() * 1000)}})
TS = [x["t"] // 1000 for x in c]; PX = [float(x["c"]) for x in c]
sp = lambda t: PX[max(bisect.bisect_right(TS, t) - 1, 0)]
temp = json.load(open("tempranos.json"))
cands = [w for w, v in temp.items() if len(v) >= MIN_GANADORES]
res = json.load(open("resultados.json")) if os.path.exists("resultados.json") else {}
os.makedirs("hist", exist_ok=True)
for w in cands:
    if w in res: continue
    s = (get(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [w, {"limit": 1000}]}) or {}).get("result") or []
    if len(s) == 1000:
        dias = max((s[0]["blockTime"] - s[-1]["blockTime"]) / 86400, 0.01)
        if 1000 / dias > 200: res[w] = {"descartada": f"bot ({1000/dias:.0f} tx/día)"}; continue
    if not s or s[0]["blockTime"] < time.time() - 10 * 86400: res[w] = {"descartada": "inactiva >10 días"}; continue
    txs, antes = [], None
    for _ in range(60):
        d = get(f"https://api.helius.xyz/v0/addresses/{w}/transactions?api-key={K}&limit=100" + (f"&before={antes}" if antes else ""))
        if not d: break
        txs += d; antes = d[-1]["signature"]
        if d[-1]["timestamp"] < T0 or len(d) < 100: break
    ops = []
    for t in sorted(txs, key=lambda x: x["timestamp"]):
        if t["timestamp"] < T0 or t.get("transactionError"): continue
        a = next((x for x in t.get("accountData", []) if x["account"] == w), None)
        sol = (a["nativeBalanceChange"] if a else 0) / 1e9; tok = collections.defaultdict(float)
        for x in t.get("accountData", []):
            for b in x.get("tokenBalanceChanges", []):
                if b["userAccount"] == w: tok[b["mint"]] += int(b["rawTokenAmount"]["tokenAmount"]) / 10 ** b["rawTokenAmount"]["decimals"]
        sol += tok.pop(WSOL, 0); est = sum(tok.pop(m, 0) for m in EST); tok = {m: v for m, v in tok.items() if v}
        if len(tok) != 1: continue
        m, q = next(iter(tok.items())); usd = sol * sp(t["timestamp"]) + est
        if usd == 0 or (usd > 0) == (q > 0) or abs(usd) < 1: continue
        ops.append({"t": t["timestamp"], "mint": m, "q": q, "usd": usd})
    json.dump(ops, open(f"hist/{w}.json", "w"))
    cubre = (time.time() - ops[0]["t"]) / 86400 if ops else 0
    # PnL realizado (coste medio) y copia
    pos = collections.defaultdict(lambda: [0.0, 0.0]); mes = collections.defaultdict(float); por_token = collections.defaultdict(float)
    mia = collections.defaultdict(lambda: [0.0, 0.0, 0.0]); caja = 0.0; invertido = 0.0; aperturas = {}; dur = []
    for o in ops:
        p = pos[o["mint"]]; px = abs(o["usd"] / o["q"]); mm = mia[o["mint"]]
        if o["q"] > 0:
            if p[0] <= 0: aperturas[o["mint"]] = o["t"]
            p[0] += o["q"]; p[1] += -o["usd"]
            if mm[2] < 500:
                gasto = min(100, 500 - mm[2]); mm[0] += gasto * 0.99 / (px * 1.03); mm[1] += gasto; mm[2] += gasto; caja -= gasto; invertido += gasto
        elif p[0] > 0:
            f = min(-o["q"] / p[0], 1); base = p[1] * f; g = o["usd"] - base
            mes[time.strftime("%Y-%m", time.gmtime(o["t"]))] += g; por_token[o["mint"]] += g
            p[1] -= base; p[0] = max(p[0] + o["q"], 0)
            if f >= 0.99 and o["mint"] in aperturas: dur.append(o["t"] - aperturas.pop(o["mint"]))
            if mm[0] > 0:
                vend = mm[0] * f; caja += vend * px * 0.97 * 0.99; mm[1] *= 1 - f; mm[0] -= vend
    abiertas = {m: v for m, v in mia.items() if v[0] > 0}
    total = sum(por_token.values()); mejor = max(por_token.values(), default=0)
    res[w] = {"ganadores": len(temp[w]), "ops": len(ops), "dias": round(cubre), "ops_dia": round(len(ops) / max(cubre, 1), 1),
              "pnl": round(total), "meses": {k: round(v) for k, v in sorted(mes.items())},
              "meses_pos": sum(1 for v in mes.values() if v > 0), "n_meses": len(mes),
              "mejor_token_pct": round(100 * mejor / total) if total > 0 else None,
              "dur_mediana_h": round(sorted(dur)[len(dur) // 2] / 3600, 1) if dur else None,
              "copia_caja": round(caja), "copia_invertido": round(invertido), "copia_abiertas": {m: v[0] for m, v in abiertas.items()},
              "historial_completo": bool(txs) and txs[-1]["timestamp"] < T0}
    json.dump(res, open("resultados.json", "w"), indent=1)
    print(w[:8], res[w]["ops"], "ops", res[w]["pnl"], "$", res[w]["meses"], "copia", res[w]["copia_caja"], flush=True)
