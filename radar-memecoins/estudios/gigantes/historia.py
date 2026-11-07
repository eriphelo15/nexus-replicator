"""Reconstruye la historia de cada token desde su nacimiento y calcula rasgos tempranos.

Uso: python historia.py candidatos.json salida.csv
Cada candidato: {"mint", "simbolo", "nacimiento", "pools": [[creado, direccion, dex], ...]}
"""
import json
import statistics as st
import sys
import time
import urllib.request
from datetime import datetime

H = {"User-Agent": "Mozilla/5.0"}
G = "https://api.geckoterminal.com/api/v2/networks/solana"


def g(u):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30))
        except Exception:
            time.sleep(10 * (i + 1))
    return {}


def velas(pool, marco, hasta, limite=1000):
    d = g(f"{G}/pools/{pool}/ohlcv/{marco}&limit={limite}&currency=usd&before_timestamp={int(hasta)}")
    time.sleep(2.6)
    return sorted(tuple(v) for v in (d.get("data", {}).get("attributes", {}).get("ohlcv_list") or []))


def unir(listas):
    por = {}
    for lista in listas:
        for v in lista:
            if v[0] not in por or v[5] > por[v[0]][5]:
                por[v[0]] = v
    return [por[k] for k in sorted(por)]


def rasgos(c, suministro):
    t0 = datetime.fromisoformat(c["nacimiento"].replace("Z", "+00:00")).timestamp()
    pools = [p[1] for p in c["pools"][:3]]
    v5 = unir([velas(p, "minute?aggregate=5", t0 + 72 * 3600) for p in pools])
    v1h = unir([velas(p, "hour?aggregate=1", time.time() + 3600) for p in pools])
    # Solo velas con volumen real y precio de cierre: los pools secundarios casi vacíos
    # dejan mechas absurdas (un token "valía" $409,000M por una sola operación).
    v5 = [v for v in v5 if v[0] >= t0 and v[5] >= 50]
    v1h = [v for v in v1h if v[5] >= 200]
    if not v5:
        return None
    mc = lambda precio: precio * suministro

    def hito(nivel, serie):
        return next((round((v[0] - t0) / 60) for v in serie if mc(v[4]) >= nivel), None)

    todas = unir([v5, [v for v in v1h if v[0] > v5[-1][0]]])
    r = {"simbolo": c["simbolo"], "mint": c["mint"], "nacimiento": c["nacimiento"][:16],
         "dex_inicial": c["pools"][0][2]}
    for nivel, nombre in [(1e5, "min_a_100k"), (1e6, "min_a_1m"), (5e6, "min_a_5m")]:
        r[nombre] = hito(nivel, todas)
    ath = max(todas, key=lambda v: v[4])
    r["ath_mc_m"] = round(mc(ath[4]) / 1e6, 2)
    r["dias_hasta_ath"] = round((ath[0] - t0) / 86400, 1)
    r["mc_ahora_m"] = round(mc(todas[-1][4]) / 1e6, 2)
    r["ahora_vs_ath"] = round(todas[-1][4] / ath[4], 2)
    # Caídas soportadas antes de llegar a $1M: la peor caída desde un máximo previo
    # y cuántas veces cayó un 50%+ y luego superó ese máximo ("murió y volvió").
    limite = next((i for i, v in enumerate(todas) if mc(v[4]) >= 1e6), len(todas))
    pico, peor, resurrecciones, en_caida, pico_caida = 0, 0, 0, False, 0
    for v in todas[:limite + 1]:
        if v[4] > pico:
            if en_caida and v[4] > pico_caida:
                resurrecciones += 1
                en_caida = False
            pico = v[4]
        caida = 1 - v[4] / pico if pico else 0
        peor = max(peor, caida)
        if caida >= 0.5 and not en_caida:
            en_caida, pico_caida = True, pico
    r["peor_caida_antes_1m"] = round(peor, 2)
    r["murio_y_volvio"] = resurrecciones
    # Forma de las 3 primeras horas: % de velas de 5 min al alza y regularidad.
    tres = [v for v in v5 if v[0] < t0 + 3 * 3600 and v[1] > 0]
    rets = [v[4] / v[1] - 1 for v in tres]
    r["velas_3h"] = len(tres)
    r["pct_velas_alza_3h"] = round(sum(x > 0 for x in rets) / len(rets), 2) if rets else None
    r["desv_ret_3h"] = round(st.pstdev(rets), 3) if len(rets) > 1 else None
    for horas in (1, 6, 24):
        vs = [v for v in todas if v[0] < t0 + horas * 3600]
        r[f"vol_{horas}h_k"] = round(sum(v[5] for v in vs) / 1e3)
        r[f"mc_{horas}h_k"] = round(mc(vs[-1][4]) / 1e3) if vs else None
    return r


if __name__ == "__main__":
    import csv
    cands = json.load(open(sys.argv[1]))
    filas = []
    for c in cands:
        info = g(f"{G}/tokens/{c['mint']}")
        time.sleep(2.6)
        a = info.get("data", {}).get("attributes", {})
        precio, fdv = float(a.get("price_usd") or 0), float(a.get("fdv_usd") or 0)
        if not precio or not fdv:
            print("sin precio:", c["simbolo"], flush=True)
            continue
        r = rasgos(c, fdv / precio)
        if r:
            filas.append(r)
            print(r["simbolo"], r["ath_mc_m"], r["min_a_1m"], flush=True)
    with open(sys.argv[2], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
