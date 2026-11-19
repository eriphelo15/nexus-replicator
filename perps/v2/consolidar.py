"""Cartera consolidada de los 10 traders del bot (10% del capital cada uno), copia simulada de 90 días.
Misma lógica que simular_copia.simular (apalancamiento máx. 3x por porción, comisión + deslizamiento, sin funding),
guardando la curva horaria de cada porción y la ganancia de cada cierre (para PF y % de acierto)."""
import json, sys, time, bisect, collections
sys.path.insert(0, ".."); import simular_copia as S
CAP = 10_000
TR = json.load(open("../bot/config.json"))["traders"]

def simular(dir_, fills):
    fills = sorted([f for f in fills if "/" not in f["coin"] and not f["coin"].startswith("@")], key=lambda f: f["time"])
    t0, t1 = fills[0]["time"], fills[-1]["time"]
    S._velas.clear()
    for c in {f["coin"] for f in fills}: S.velas(c, t0 - 3600_000, int(time.time() * 1000))
    cap_suyo = S.capital_suyo(dir_)
    suya, mia, entrada, ultimo = collections.defaultdict(float), collections.defaultdict(float), {}, {}
    caja = 1.0; cierres = []                        # porción normalizada a 1
    def equity(t): return caja + sum(q * (S.precio(c, t, ultimo.get(c, entrada.get(c, 0))) - entrada[c]) for c, q in mia.items() if q)
    def operar(c, nueva, px):
        nonlocal caja
        q = mia[c]
        if abs(nueva - q) < 1e-15: return
        caja -= abs(nueva - q) * px * (S.COMISION + S.DESLIZ["hip3" if ":" in c else "normal"])
        if q and (nueva * q <= 0 or abs(nueva) < abs(q)):
            cerrar = q if nueva * q <= 0 else q - nueva; g = cerrar * (px - entrada[c]); caja += g; cierres.append(g)
        if nueva and q * nueva <= 0: entrada[c] = px
        elif nueva and abs(nueva) > abs(q): entrada[c] = (entrada[c] * q + px * (nueva - q)) / nueva
        mia[c] = nueva
    curva = {}; i = 0
    h = (t0 // 3600_000 + 1) * 3600_000; fin = (int(time.time() * 1000) // 3600_000) * 3600_000
    while h <= fin:
        while i < len(fills) and fills[i]["time"] <= h:
            f = fills[i]; c, px = f["coin"], float(f["px"]); ultimo[c] = px
            suya[c] = float(f["startPosition"]) + float(f["sz"]) * (1 if f["side"] == "B" else -1)
            k = equity(f["time"]) / S.capital_suyo(dir_)(f["time"]) if False else equity(f["time"]) / cap_suyo(f["time"])
            obj = {cc: q * k for cc, q in suya.items()}
            noc = sum(abs(q) * S.precio(cc, f["time"], ultimo.get(cc, px)) for cc, q in obj.items())
            s = min(1.0, S.APALANCAMIENTO_MAX * equity(f["time"]) / noc) if noc else 1.0
            operar(c, obj[c] * s, px); i += 1
        curva[h] = equity(h); h += 3600_000
    return curva, cierres

curvas, todos = {}, []
for d, info in TR.items():
    try: fills = json.load(open(f"fills/{d}.json"))
    except FileNotFoundError: fills = json.load(open(f"../fills_{d[:10]}.json"))
    curva, cierres = simular(d, fills); curvas[info["nombre"]] = curva; todos += [g * CAP * 0.1 for g in cierres]
    print(info["nombre"], f"{list(curva.values())[-1] - 1:+.1%}", len(cierres), "cierres", flush=True)
horas = sorted(set().union(*[set(c) for c in curvas.values()]))
inicio = min(min(c) for c in curvas.values())  # 03ef: la API solo da sus últimos 10,000 fills (desde el 30-oct); antes, porción sin operar
horas = [h for h in horas if h >= inicio]
def val(c, h):
    ks = sorted(c); j = bisect.bisect_right(ks, h) - 1
    return c[ks[j]] if j >= 0 else c[ks[0]]
eq = [CAP * 0.1 * sum(val(c, h) / val(c, inicio) for c in curvas.values()) for h in horas]
pico, dd, ddmax = eq[0], 0, 0
for v in eq: pico = max(pico, v); ddmax = max(ddmax, 1 - v / pico)
dias = collections.OrderedDict()
for h, v in zip(horas, eq): dias[time.strftime("%Y-%m-%d", time.gmtime(h / 1000))] = v
dv = list(dias.values()); rd = [dv[j] / dv[j - 1] - 1 for j in range(1, len(dv))]
semanas = [dv[j] / dv[j - 7] - 1 for j in range(7, len(dv), 7)]
meses = collections.OrderedDict()
for d_, v in dias.items(): meses.setdefault(d_[:7], [v, v]); meses[d_[:7]][1] = v
prev = eq[0]; mres = {}
for m, (a, b) in meses.items(): mres[m] = b / prev - 1; prev = b
gan = [g for g in todos if g > 0]; per = [g for g in todos if g < 0]
r = {"desde": time.strftime("%Y-%m-%d", time.gmtime(inicio / 1000)), "hasta": list(dias)[-1], "dias": len(dv),
     "capital_final": round(eq[-1]), "crecimiento": round(eq[-1] / CAP - 1, 4), "caida_max": round(ddmax, 4),
     "pf": round(sum(gan) / -sum(per), 2), "acierto": round(len(gan) / len(todos), 3), "cierres": len(todos),
     "ganancia_media": round(sum(gan) / len(gan), 2), "perdida_media": round(sum(per) / len(per), 2),
     "dias_positivos": f"{sum(x > 0 for x in rd)}/{len(rd)}", "semanas_positivas": f"{sum(x > 0 for x in semanas)}/{len(semanas)}",
     "peor_dia": round(min(rd), 4), "mejor_dia": round(max(rd), 4), "meses": {k: round(v, 4) for k, v in mres.items()},
     "por_trader": {n: round(val(c, horas[-1]) / val(c, inicio) - 1, 4) for n, c in curvas.items()}}
json.dump(r, open("consolidado.json", "w"), indent=1); print(json.dumps(r, indent=1))
