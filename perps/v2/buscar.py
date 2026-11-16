"""Búsqueda v2 de traders de Hyperliquid para copiar (prioriza largo plazo).
1) Clasificación completa: capital >= $10K, ganancia histórica >= $30K, ROI histórico >= 50%, activo este mes.
2) Historial (portfolio): >= 6 meses, >= 70% de meses positivos, peor caída <= 40% del capital, ganando en los últimos 90 días.
3) Fills de 90 días: >= 20 cierres y duración mediana >= 1 h (los scalpers de segundos no se pueden copiar).
4) Copia simulada (simular_copia.simular, sin reglas de fondeo, $10K, apalancamiento máx. 3x)."""
import json, os, sys, time, statistics as st, urllib.request as U
sys.path.insert(0, ".."); import simular_copia as S
def post(b):
    for i in range(6):
        try: return json.load(U.urlopen(U.Request("https://api.hyperliquid.xyz/info", data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}), timeout=40))
        except Exception: time.sleep(4 * (i + 1))
W = lambda x, k: {a: b for a, b in x["windowPerformances"]}[k]
rows = json.load(open("leaderboard.json"))["leaderboardRows"]
c1 = [x["ethAddress"] for x in rows if float(x["accountValue"]) >= 1e4 and float(W(x, "allTime")["pnl"]) >= 3e4
      and float(W(x, "allTime")["roi"]) >= 0.5 and float(W(x, "month")["vlm"]) > 0]
ahora = time.time()
# Paso 2
hist = {json.loads(l)["dir"]: json.loads(l) for l in open("consistencia.jsonl")} if os.path.exists("consistencia.jsonl") else {}
f2 = open("consistencia.jsonl", "a")
for d in c1:
    if d in hist: continue
    p = post({"type": "portfolio", "user": d}) or []; h = (dict(p) if isinstance(p, list) else {}).get("allTime") or {}
    pnl = [(t / 1000, float(v)) for t, v in h.get("pnlHistory", [])]; av = [(t / 1000, float(v)) for t, v in h.get("accountValueHistory", [])]
    r = {"dir": d}
    if len(pnl) >= 10:
        meses, t0, ult, k = [], pnl[0][0], pnl[0][1], 1
        for t, v in pnl:
            if t >= t0 + 30 * 86400 * k: meses.append(v - ult); ult = v; k += 1
        meses.append(pnl[-1][1] - ult)
        base = st.median([v for _, v in av if v > 100] or [1.0]); pico, peor = -1e18, 0.0
        for _, v in pnl: pico = max(pico, v); peor = max(peor, pico - v)
        p90 = [v for t, v in pnl if t >= ahora - 90 * 86400]
        r.update(meses=len(meses), meses_pos=sum(m > 0 for m in meses), pnl_meses=[round(m) for m in meses], capital=round(base),
                 peor_caida=round(peor / max(base, 1), 3), pnl_total=round(pnl[-1][1]), pnl_90d=round(p90[-1] - p90[0]) if len(p90) > 1 else 0,
                 dias=round((pnl[-1][0] - pnl[0][0]) / 86400))
    hist[d] = r; f2.write(json.dumps(r) + "\n"); f2.flush(); time.sleep(0.4)
c2 = [r for r in hist.values() if r.get("meses", 0) >= 6 and r["meses_pos"] / r["meses"] >= 0.7 and r["peor_caida"] <= 0.4 and r["pnl_90d"] > 0]
print("paso1", len(c1), "paso2", len(c2), flush=True)
# Paso 3 y 4
res = json.load(open("resultados.json")) if os.path.exists("resultados.json") else {}
os.makedirs("fills", exist_ok=True)
for r in c2:
    d = r["dir"]
    if d in res: continue
    fills, t = [], int((ahora - 90 * 86400) * 1000)
    for _ in range(15):
        f = post({"type": "userFillsByTime", "user": d, "startTime": t, "aggregateByTime": True}) or []
        if not f: break
        fills += f; t = f[-1]["time"] + 1
        if len(f) < 2000: break
    abre, dur, cierres = {}, [], 0
    for z in sorted(fills, key=lambda z: z["time"]):
        k = z["coin"]; a = float(z["startPosition"]); s = float(z["sz"]) * (1 if z["side"] == "B" else -1); b = a + s
        if abs(a) < 1e-12 and abs(b) > 0: abre[k] = z["time"]
        if abs(b) < 1e-9 * max(abs(a), 1) or a * b < 0:
            cierres += 1
            if k in abre: dur.append((z["time"] - abre.pop(k)) / 3.6e6)
            if a * b < 0: abre[k] = z["time"]
    dm = st.median(dur) if dur else 0
    out = {**r, "fills": len(fills), "cierres": cierres, "dur_h": round(dm, 2)}
    if cierres < 20 or dm < 1: out["descartado"] = "pocas operaciones" if cierres < 20 else "scalper"
    else:
        json.dump(fills, open(f"fills/{d}.json", "w"))
        S._velas.clear()
        s = S.simular(d, fills, reglas=False)
        if s: out.update(copia_ret=round(s["ret"], 3), copia_dd=round(s["peor_dd"], 3))
    res[d] = out; json.dump(res, open("resultados.json", "w"), indent=1)
    print(d[:10], out.get("descartado") or f"{out.get('copia_ret')} dd {out.get('copia_dd')}", flush=True)
print("fin")
