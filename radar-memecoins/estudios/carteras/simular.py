"""Copia simulada con capital real limitado sobre hist/<cartera>.json.
$5,000; cada compra suya = 2% del capital ($100) si hay efectivo; tope 10% ($500) por token;
3% de deslizamiento + 1% de comisión por lado; vende la misma fracción que él.
Lo que sigue abierto al final se valora al precio actual de Jupiter (0 si no tiene precio)."""
import json, os, sys, time, collections, urllib.request as U
CAP, LOTE, TOPE, DESL, COM = 5000, 100, 500, 0.03, 0.01
res = json.load(open("resultados.json")); precios = json.load(open("precios.json")) if os.path.exists("precios.json") else {}
def sim(ops):
    caja = CAP; mia = collections.defaultdict(lambda: [0.0, 0.0]); suya = collections.defaultdict(float); n = 0
    for o in ops:
        px = abs(o["usd"] / o["q"]); m = o["mint"]
        if o["q"] > 0:
            suya[m] += o["q"]
            g = min(LOTE, TOPE - mia[m][1], caja)
            if g >= 10: mia[m][0] += g * (1 - COM) / (px * (1 + DESL)); mia[m][1] += g; caja -= g; n += 1
        elif suya[m] > 0:
            f = min(-o["q"] / suya[m], 1); suya[m] = max(suya[m] + o["q"], 0)
            v = mia[m][0] * f; caja += v * px * (1 - DESL) * (1 - COM); mia[m][0] -= v; mia[m][1] *= 1 - f
            if mia[m][0] <= 1e-12: mia[m] = [0.0, 0.0]
    return caja, {m: v[0] for m, v in mia.items() if v[0] > 0}, n
salida = {}
for w, r in res.items():
    if "descartada" in r: continue
    caja, ab, n = sim(json.load(open(f"hist/{w}.json")))
    falta = [m for m in ab if m not in precios]
    for i in range(0, len(falta), 20):
        time.sleep(1.5)
        try: d = json.load(U.urlopen(f"https://lite-api.jup.ag/price/v3?ids={','.join(falta[i:i+20])}", timeout=30))
        except Exception: d = {}
        for m in falta[i:i+20]: precios[m] = float((d.get(m) or {}).get("usdPrice", 0))
    val = sum(q * precios.get(m, 0) for m, q in ab.items())
    salida[w] = {"final": round(caja + val), "ret_pct": round(100 * (caja + val - CAP) / CAP, 1), "caja": round(caja), "abierto": round(val), "compras": n}
json.dump(precios, open("precios.json", "w")); json.dump(salida, open("copia.json", "w"), indent=1)
for w, s in sorted(salida.items(), key=lambda x: -x[1]["ret_pct"])[:15]:
    r = res[w]; print(w, s["ret_pct"], "% |", r["dias"], "d", r["ops_dia"], "ops/d | pnl", r["pnl"], r["meses"], "| mejor token", r["mejor_token_pct"], "%")
