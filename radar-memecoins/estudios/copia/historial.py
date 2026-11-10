"""Revisión independiente (10-nov-2026) de copiar la cartera con TODO su historial. Ver copybot/ESTUDIO_HISTORIAL.md.

Uso: python historial.py   (lee operaciones.jsonl, seleccion.json y sol.json; no usa la red)
Diferencia con topes.py: las posiciones aún abiertas se valoran a SU último precio de operación, no al precio
actual de Jupiter. Por eso los niveles salen más altos que en topes.py; lo fiable es la forma, no el nivel.
"""
import bisect, collections, json, statistics as st, time

solh = sorted((v[0], v[4]) for v in json.load(open("sol.json"))); stt = [a for a, _ in solh]
ps = lambda t: solh[max(bisect.bisect_right(stt, t) - 1, 0)][1]
usd = lambda o: abs(o.get("USDC", 0) + o.get("USDT", 0) + o.get("sol", 0) * ps(o["t"]))
ops = sorted((o for o in (json.loads(l) for l in open("operaciones.jsonl")) if usd(o) >= 1), key=lambda o: o["t"])
D = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))
T = lambda s: time.mktime(time.strptime(s, "%Y-%m-%d"))
EXPO = 259149      # su exposición máxima (la misma cifra que usa config.ejemplo.json)


def cartera():
    per = collections.defaultdict(lambda: dict(b=0, s=0, comprado=0, tok=0, t1=0))
    for o in ops:
        p = per[o["mint"]]; p["t1"] = o["t"]; p["tok"] += o["cantidad"]
        if o["cantidad"] > 0: p["b"] += usd(o); p["comprado"] += o["cantidad"]
        else: p["s"] += usd(o)
    filas = [(m, p["s"] - p["b"], p) for m, p in per.items()]
    cerr = [f for f in filas if f[2]["b"] > 0 and f[2]["tok"] <= 0.02 * f[2]["comprado"]]
    ab = [f for f in filas if f[2]["b"] > 0 and f not in cerr]
    tb = sum(p["b"] for _, _, p in filas); x = sorted((v for _, v, _ in cerr), reverse=True)
    print(f"operaciones {len(ops)} | {D(ops[0]['t'])} → {D(ops[-1]['t'])} | tokens {len(filas)}, cerrados {len(cerr)}, abiertos {len(ab)}")
    print(f"comprado ${tb:,.0f} | resultado de los cerrados ${sum(x):,.0f} ({sum(x) / tb:+.1%} de lo comprado)")
    print(f"ganadores {sum(v > 0 for v in x)}/{len(x)} | token típico (mediana) ${st.median(x):,.0f} | 5 mejores ${sum(x[:5]):,.0f} | 5 peores ${sum(x[-5:]):,.0f}")
    print(f"abiertos: ${-sum(v for _, v, _ in ab):,.0f} de coste aún dentro")
    pm = collections.defaultdict(float)
    for _, v, p in cerr: pm[time.strftime("%Y-%m", time.gmtime(p["t1"]))] += v
    print("cerrados por mes de cierre:", {k: round(v) for k, v in sorted(pm.items())})
    sel = set(json.load(open("seleccion.json")))
    print(f"los 29 tokens de seleccion.json: flujo neto ${sum(v for m, v, _ in filas if m in sel):,.0f} | el resto: ${sum(v for m, v, _ in filas if m not in sel):,.0f}")
    bu = [usd(o) for o in ops if o["cantidad"] > 0]
    print(f"sus compras: {len(bu)}, mediana ${st.median(bu):,.0f}, la mayor ${max(bu):,.0f}")


def sim(ops, capital=5000, tope=.10, desc=0.03, descv=None, com=0.01, minop=1.0):
    """Devuelve (resultado final, peor momento) como fracción del capital."""
    descv = desc if descv is None else descv
    f = capital / EXPO; caja = capital; pos = collections.defaultdict(lambda: [0., 0.])
    suyo = collections.defaultdict(float); last = {}; peor = capital
    for o in ops:
        m = o["mint"]; u = usd(o); p = u / abs(o["cantidad"]); last[m] = p
        if o["cantidad"] > 0:
            suyo[m] += o["cantidad"]
            x = min(u * f, (tope * capital if tope else 1e18) - pos[m][1], caja / (1 + com))
            if x < minop: continue
            caja -= x * (1 + com); pos[m][0] += x / (p * (1 + desc)); pos[m][1] += x
        else:
            fr = min(1, -o["cantidad"] / suyo[m]) if suyo[m] > 0 else 0; suyo[m] = max(0, suyo[m] + o["cantidad"])
            q = pos[m][0] * fr
            if q <= 0: continue
            caja += q * p * (1 - descv) * (1 - com); pos[m][1] -= pos[m][1] * fr; pos[m][0] -= q
        peor = min(peor, caja + sum(q * last[k] for k, (q, _) in pos.items() if q > 0))
    return (caja + sum(q * last[k] for k, (q, _) in pos.items()) - capital) / capital, peor / capital - 1


if __name__ == "__main__":
    cartera()
    DES = ((.01, .01), (.03, .03), (.02, .075), (.05, .05))
    print("\nCopia con $5.000, todo el historial: resultado (peor momento). Columnas = peor precio en compra/venta")
    print("              " + "   ".join(f"{a:.0%}/{b:.1%}".ljust(13) for a, b in DES))
    for tope in (None, .05, .10, .15, .20, .30):
        print(("sin tope" if not tope else f"tope {tope:.0%}").ljust(13),
              "   ".join(f"{r[0]:+5.0%} ({r[1]:+4.0%})" for r in (sim(ops, tope=tope, desc=a, descv=b) for a, b in DES)))
    print("\nPor tramos, empezando de cero en cada uno (tope 10 %)")
    for a, b in (("2026-08-09", "2026-09-09"), ("2026-09-09", "2026-10-09"), ("2026-10-09", "2026-11-10")):
        sub = [o for o in ops if T(a) <= o["t"] < T(b)]
        r1 = sim(sub); r2 = sim(sub, desc=.02, descv=.075); r0 = sim(sub, tope=None)
        print(f"  {a} → {b}: {len(sub)} ops | 3%/3%: {r1[0]:+.0%} (peor {r1[1]:+.0%}) | 2%/7.5%: {r2[0]:+.0%} | sin tope: {r0[0]:+.0%}")
    print("\n¿El tope que mejor iba en ago-sep era el mejor en oct-nov? (3%/3%)")
    for lab, a, b in (("ago-sep", "2026-08-09", "2026-10-01"), ("oct-nov", "2026-10-01", "2026-11-10")):
        sub = [o for o in ops if T(a) <= o["t"] < T(b)]
        print(" ", lab, " ".join(("sin" if not t else f"{t:.0%}") + f" {sim(sub, tope=t)[0]:+.0%}" for t in (None, .05, .10, .15, .20, .30)))
