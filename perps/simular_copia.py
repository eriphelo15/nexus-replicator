"""Simula copiar a un trader de perpetuos de Hyperliquid en una cuenta de fondeo de $10K.

Uso: python simular_copia.py
Para cada candidato (90 días de fills):
- Su posición en cada moneda se escala por (nuestro capital / su capital) y luego se limita a
  APALANCAMIENTO_MAX veces nuestro capital en total.
- Cada cambio de posición suyo lo replicamos con COMISION + DESLIZ (más alto en los mercados
  HIP-3 "xyz:", que son menos líquidos). El retraso de segundos se recoge en ese deslizamiento.
- La cuenta se valora cada hora con velas de 1 h. Reglas de fondeo: si en el día se pierde un
  PERDIDA_DIA del capital al inicio del día, se cierra todo hasta el día siguiente; si el capital
  cae un PERDIDA_TOTAL bajo el inicial, la cuenta se pierde.
No incluye el funding (pagos entre largos y cortos).
"""
import json, time, bisect, collections, urllib.request as U

CAPITAL = 10_000
APALANCAMIENTO_MAX = 3.0
COMISION = 0.00045            # taker de Hyperliquid
DESLIZ = {"normal": 0.0005, "hip3": 0.0015}
PERDIDA_DIA, PERDIDA_TOTAL = 0.05, 0.10
CANDIDATOS = ["0x739ccf4a", "0xf83858e5", "0x378defc3", "0xd46979f0", "0x69b05701",
              "0x1404109f", "0x8cbe593a", "0x26407a88"]


def post(b):
    for i in range(5):
        try:
            return json.load(U.urlopen(U.Request("https://api.hyperliquid.xyz/info", data=json.dumps(b).encode(),
                                                 headers={"Content-Type": "application/json"}), timeout=30))
        except Exception:
            time.sleep(3 * (i + 1))


_velas = {}
def velas(coin, t0, t1):
    if coin not in _velas:
        v = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": t0, "endTime": t1}}) or []
        _velas[coin] = ([x["t"] for x in v], [float(x["c"]) for x in v])
        time.sleep(0.3)
    return _velas[coin]


def precio(coin, t, fallback):
    ts, cs = _velas.get(coin, ([], []))
    i = bisect.bisect_right(ts, t) - 1
    return cs[i] if i >= 0 else fallback


def capital_suyo(dir_):
    p = post({"type": "portfolio", "user": dir_}) or []
    av = [(t, float(v)) for t, v in dict(p).get("allTime", {}).get("accountValueHistory", [])]
    ts = [t for t, _ in av]
    return lambda t: max(av[max(bisect.bisect_right(ts, t) - 1, 0)][1], 1.0) if av else 1.0


def simular(dir_, fills, reglas=True):
    fills = sorted([f for f in fills if "/" not in f["coin"] and not f["coin"].startswith("@")], key=lambda f: f["time"])
    if not fills:
        return None
    t0, t1 = fills[0]["time"], fills[-1]["time"]
    for c in {f["coin"] for f in fills}:
        velas(c, t0 - 3600_000, t1 + 3600_000)
    cap_suyo = capital_suyo(dir_)
    suya = collections.defaultdict(float)      # su posición (unidades)
    mia = collections.defaultdict(float)       # nuestra posición (unidades)
    entrada = {}                               # precio de referencia de nuestra posición
    caja = CAPITAL                             # efectivo + pnl realizado
    ultimo = {}
    def equity(t):
        return caja + sum(q * (precio(c, t, ultimo.get(c, entrada.get(c, 0))) - entrada[c]) for c, q in mia.items() if q)
    def operar(c, nueva, px, t):
        nonlocal caja
        q = mia[c]
        if abs(nueva - q) < 1e-12:
            return
        coste = abs(nueva - q) * px * (COMISION + DESLIZ["hip3" if ":" in c else "normal"])
        caja -= coste
        if q and (nueva * q <= 0 or abs(nueva) < abs(q)):           # reduce o cierra: realiza pnl
            cerrar = q if nueva * q <= 0 else q - nueva
            caja += cerrar * (px - entrada[c])
        if nueva and (q * nueva <= 0):
            entrada[c] = px
        elif nueva and abs(nueva) > abs(q):                          # aumenta: precio medio
            entrada[c] = (entrada[c] * q + px * (nueva - q)) / nueva
        mia[c] = nueva
    eventos = [("f", f["time"], f) for f in fills]
    h = (t0 // 3600_000 + 1) * 3600_000
    while h <= t1 + 3600_000:
        eventos.append(("h", h, None)); h += 3600_000
    eventos.sort(key=lambda e: e[1])
    dia, eq_dia, bloqueado, perdida, pico, peor_dd, dias_cortados = None, CAPITAL, False, False, CAPITAL, 0.0, 0
    for tipo, t, f in eventos:
        d = time.gmtime(t / 1000)[:3]
        if d != dia:
            dia, eq_dia, bloqueado = d, equity(t), False
        if tipo == "f":
            c, px = f["coin"], float(f["px"]); ultimo[c] = px
            suya[c] = float(f["startPosition"]) + float(f["sz"]) * (1 if f["side"] == "B" else -1)
            if perdida or bloqueado:
                continue
            k = equity(t) / cap_suyo(t)
            objetivo = {cc: q * k for cc, q in suya.items()}
            nocional = sum(abs(q) * precio(cc, t, ultimo.get(cc, px)) for cc, q in objetivo.items())
            s = min(1.0, APALANCAMIENTO_MAX * equity(t) / nocional) if nocional else 1.0
            operar(c, objetivo[c] * s, px, t)
        eq = equity(t)
        pico = max(pico, eq); peor_dd = max(peor_dd, 1 - eq / pico)
        if reglas and not perdida:
            if eq <= CAPITAL * (1 - PERDIDA_TOTAL):
                perdida = True
            if eq <= eq_dia * (1 - PERDIDA_DIA) and not bloqueado:
                bloqueado = True; dias_cortados += 1
            if perdida or bloqueado:
                for c in list(mia):
                    operar(c, 0.0, precio(c, t, ultimo.get(c, 0)), t)
    final = equity(t1 + 3600_000)
    return {"final": final, "ret": final / CAPITAL - 1, "peor_dd": peor_dd, "cuenta_perdida": perdida,
            "dias_cortados": dias_cortados, "dias": (t1 - t0) / 86400_000}


if __name__ == "__main__":
    ops = {x["dir"][:10]: x for x in json.load(open("operativa.json"))}
    for c in CANDIDATOS:
        fills = json.load(open(f"fills_{c}.json"))
        r_sin = simular(ops[c]["dir"], fills, reglas=False)
        r = simular(ops[c]["dir"], fills, reglas=True)
        print(f"{c} | {r['dias']:.0f} d | sin reglas: {r_sin['ret']:+.1%} (caída máx {r_sin['peor_dd']:.0%}) | "
              f"con reglas de fondeo: {r['ret']:+.1%} (caída máx {r['peor_dd']:.0%}, días cortados {r['dias_cortados']}, "
              f"{'CUENTA PERDIDA' if r['cuenta_perdida'] else 'cuenta viva'}) | él: ${ops[c]['pnl_90d']:,.0f}", flush=True)
