"""Copia de su cartera de Solana (todo el historial) con y sin tope por token, para dos tamaños de cuenta.

Precio de copia = el suyo con un 3% en contra (medición segundo a segundo) y 1% de comisión por lado.
El factor de copia = nuestro capital / su máxima exposición. Las posiciones abiertas al final se
valoran al precio actual de Jupiter (0 si el token ya no cotiza).
"""
import json, bisect, collections, time, urllib.request as U
DES, COM = 0.03, 0.01
solh = sorted((v[0], v[4]) for v in json.load(open("sol.json"))); st = [a for a, _ in solh]
def ps(t):  # precio de SOL; antes del rango descargado se usa el primero conocido
    return solh[max(bisect.bisect_right(st, t) - 1, 0)][1]
usd = lambda o: abs(o.get("USDC", 0) + o.get("USDT", 0) + o.get("sol", 0) * ps(o["t"]))
import os
DESDE = int(os.environ.get("DESDE", "0"))
ops = sorted([o for o in (json.loads(l) for l in open("operaciones.jsonl")) if usd(o) >= 1 and o["t"] >= DESDE], key=lambda o: o["t"])
# precios actuales (Jupiter price API, lotes de 50)
mints = sorted({o["mint"] for o in ops}); precio = {}
for i in range(0, len(mints), 50):
    try:
        d = json.load(U.urlopen(f"https://lite-api.jup.ag/price/v3?ids={','.join(mints[i:i+50])}", timeout=30))
        for m, v in d.items(): precio[m] = float((v or {}).get("usdPrice") or 0)
    except Exception: pass
    time.sleep(1)
# descartar precios actuales absurdos (más de 20x su mejor precio de operación)
pmax = collections.defaultdict(float)
for o in ops: pmax[o["mint"]] = max(pmax[o["mint"]], usd(o) / abs(o["cantidad"]))
for m in list(precio):
    if precio[m] > 20 * pmax[m]: precio[m] = 0
# su exposición máxima
coste = collections.defaultdict(float); tok = collections.defaultdict(float); expo = 0
for o in ops:
    m = o["mint"]
    if o["cantidad"] > 0: coste[m] += usd(o); tok[m] += o["cantidad"]
    elif tok[m] > 0:
        f = min(1, -o["cantidad"] / tok[m]); coste[m] *= 1 - f; tok[m] *= 1 - f
    expo = max(expo, sum(coste.values()))
mes = lambda t: time.strftime("%Y-%m", time.gmtime(t))
def sim(capital, tope_pct):
    factor = capital / expo; caja = capital; pos = collections.defaultdict(lambda: [0.0, 0.0])
    suyo = collections.defaultdict(float); perdidas = 0; por_mes = collections.defaultdict(float)
    for o in ops:
        m = o["mint"]; u = usd(o); p = u / abs(o["cantidad"])
        if o["cantidad"] > 0:
            suyo[m] += o["cantidad"]
            x = min(u * factor, (tope_pct * capital if tope_pct else 1e18) - pos[m][1], caja)
            if x < 1: perdidas += 1; continue
            caja -= x * (1 + COM); pos[m][0] += x / (p * (1 + DES)); pos[m][1] += x
        else:
            fr = min(1, -o["cantidad"] / suyo[m]) if suyo[m] > 0 else 0; suyo[m] = max(0, suyo[m] + o["cantidad"])
            q = pos[m][0] * fr; ingreso = q * p * (1 - DES) * (1 - COM); coste_v = pos[m][1] * fr
            caja += ingreso; pos[m][0] -= q; pos[m][1] -= coste_v; por_mes[mes(o["t"])] += ingreso - coste_v
    abiertas = sum(q * precio.get(m, 0) for m, (q, _) in pos.items())
    return caja + abiertas - capital, abiertas - sum(c for _, c in pos.values()), perdidas, dict(por_mes)
print(f"operaciones {len(ops)} | desde {time.strftime('%Y-%m-%d', time.gmtime(ops[0]['t']))} | su exposición máxima ${expo:,.0f}")
for capital in (5_000, round(expo)):
    print(f"\nCuenta de ${capital:,.0f} (factor {capital / expo:.2%})")
    for tope in (None, 0.10, 0.20, 0.30):
        g, abiertas, perd, pm = sim(capital, tope)
        meses = " · ".join(f"{k[5:]}: {v:+,.0f}" for k, v in sorted(pm.items()))
        print(f"  {'sin tope' if not tope else f'tope {tope:.0%}':9}: {g:>+12,.0f} ({g / capital:+.0%}) | de ello abiertas {abiertas:+,.0f} | compras no copiadas {perd} | realizado por mes: {meses}")
