"""Prueba histórica: ¿las previsiones meteorológicas públicas ganan a los precios de Kalshi?

Para cada día y ciudad:
  1. Toma la previsión de máxima de varios modelos TAL COMO SE PUBLICÓ antes de operar
     (sin mirar el futuro).
  2. La convierte en probabilidad por tramo, corrigiendo el sesgo y el error típico
     aprendidos SOLO con días anteriores (walk-forward).
  3. Compara con el precio real de Kalshi a esa hora (precio de compra, no el medio).
  4. Si la ventaja supera un umbral, "compra" 1 contrato y anota el resultado real,
     con comisiones.

    python backtest.py
"""
from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"
MESES = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# Momentos de decisión (UTC) y antelación de la previsión que es seguro usar en cada uno.
#  A: la víspera a las 20:00 UTC (15-16 h en Nueva York) con la previsión de 2 días antes.
#  B: el mismo día a las 16:00 UTC (11-12 h en Nueva York) con la previsión de 1 día antes.
#  A_optimista: como A pero con la previsión de 1 día antes, que puede incluir una
#  ejecución del modelo publicada unas horas DESPUÉS de la decisión. Le da ventaja
#  injusta al modelo a propósito: si ni así gana al mercado, no hay ventaja real.
DECISIONES = {"A_vispera": (-1, 20, "2"), "A_optimista": (-1, 20, "1"),
              "B_mismo_dia": (0, 16, "1")}
VENTANA = 60       # días de historia para estimar sesgo y error
MIN_HIST = 20
MIN_MODELOS = 3


def fecha_evento(event_ticker: str) -> date:
    code = event_ticker.split("-")[1]          # p. ej. 26OCT05
    return date(2000 + int(code[:2]), MESES[code[2:5]], int(code[5:7]))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def precio(c: dict, lado: str):
    q = c.get(lado) or {}
    return num(q.get("close_dollars", q.get("close")))


def cotizacion(velas: list, ts_decision: int):
    """Última vela cerrada antes de la decisión → (bid, ask, volumen de esa hora)."""
    previas = [c for c in velas if c["end_period_ts"] <= ts_decision]
    if not previas:
        return None
    c = max(previas, key=lambda c: c["end_period_ts"])
    if ts_decision - c["end_period_ts"] > 3 * 3600:
        return None  # cotización demasiado vieja
    bid, ask = precio(c, "yes_bid"), precio(c, "yes_ask")
    vol = num(c.get("volume_fp", c.get("volume"))) or 0.0
    if bid is None or ask is None or not (0 < bid < ask < 1):
        return None
    return bid, ask, vol


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def prob_tramo(m: dict, mu: float, sigma: float) -> float:
    """El valor oficial es un entero: P(round(X) en el tramo), X ~ N(mu, sigma)."""
    st, lo, hi = m["strike_type"], m.get("floor_strike"), m.get("cap_strike")
    if st == "between":
        p = phi((hi + 0.5 - mu) / sigma) - phi((lo - 0.5 - mu) / sigma)
    elif st == "less":
        p = phi((hi - 0.5 - mu) / sigma)
    elif st == "greater":
        p = 1 - phi((lo + 0.5 - mu) / sigma)
    else:
        return float("nan")
    return min(max(p, 0.001), 0.999)


def fee(p: float) -> float:
    return 0.07 * p * (1 - p)  # comisión taker de Kalshi por contrato (sin redondeo)


def cargar():
    mercados = json.loads((DATA / "markets.json").read_text())
    previsiones = json.loads((DATA / "forecasts.json").read_text())
    eventos = defaultdict(list)
    for m in mercados:
        if m.get("result") in ("yes", "no") and m.get("strike_type") in ("between", "less", "greater"):
            eventos[m["event_ticker"]].append(m)
    return eventos, previsiones


def media_modelos(previsiones, ciudad, lead, dia: str):
    vals = [d[lead][dia] for k, d in previsiones.items()
            if k.startswith(ciudad + "|") and lead in d and dia in d[lead]]
    return statistics.fmean(vals) if len(vals) >= MIN_MODELOS else None


def estimar(previsiones, reales, ciudad, lead, d: date):
    """Combina modelos corrigiendo el sesgo de cada uno y pesándolos por su error reciente.

    Solo usa días ya resueltos en el momento de decidir (hasta D-2)."""
    hoy = d.isoformat()
    pasados = [(d - timedelta(days=k)).isoformat() for k in range(2, VENTANA + 2)]
    pasados = [p for p in pasados if (ciudad, p) in reales]
    comps = []
    for k, dd in previsiones.items():
        if not k.startswith(ciudad + "|") or lead not in dd or hoy not in dd[lead]:
            continue
        serie = dd[lead]
        res = [reales[(ciudad, p)] - serie[p] for p in pasados if p in serie]
        if len(res) < MIN_HIST:
            continue
        sesgo = statistics.fmean(res)
        mse = statistics.fmean((r - sesgo) ** 2 for r in res) + 0.25
        comps.append((serie, sesgo, 1 / mse))
    if len(comps) < MIN_MODELOS:
        return None
    wsum = sum(w for *_, w in comps)
    mu = sum(w * (serie[hoy] + b) for serie, b, w in comps) / wsum
    res_combo = []
    for p in pasados:
        if all(p in serie for serie, *_ in comps):
            f = sum(w * (serie[p] + b) for serie, b, w in comps) / wsum
            res_combo.append(reales[(ciudad, p)] - f)
    if len(res_combo) < MIN_HIST:
        return None
    sigma = max(1.1 * math.sqrt(statistics.fmean(r * r for r in res_combo)), 1.2)
    return mu, sigma


def main():
    eventos, previsiones = cargar()
    reales = {}   # (ciudad, dia) -> temperatura oficial
    for ev, ms in eventos.items():
        vs = [num(m.get("expiration_value")) for m in ms]
        v = next((x for x in vs if x is not None), None)
        if v is not None:
            reales[(ev.split("-")[0], fecha_evento(ev).isoformat())] = v

    filas = []      # una por tramo y decisión
    for ev, ms in sorted(eventos.items(), key=lambda kv: fecha_evento(kv[0])):
        ciudad, d = ev.split("-")[0], fecha_evento(ev)
        if (ciudad, d.isoformat()) not in reales:
            continue
        for nombre, (dd, hora, lead) in DECISIONES.items():
            ts = int(datetime(d.year, d.month, d.day, hora, tzinfo=timezone.utc).timestamp()
                     + dd * 86400)
            est = estimar(previsiones, reales, ciudad, lead, d)
            if est is None:
                continue
            mu, sigma = est
            for m in ms:
                try:
                    velas = json.loads((DATA / "candles" / f"{m['ticker']}.json").read_text())
                except FileNotFoundError:
                    continue
                q = cotizacion(velas, ts)
                if not q:
                    continue
                bid, ask, vol = q
                filas.append({
                    "decision": nombre, "ciudad": ciudad, "dia": d.isoformat(),
                    "ticker": m["ticker"], "p": prob_tramo(m, mu, sigma),
                    "bid": bid, "ask": ask, "vol": vol,
                    "y": 1.0 if m["result"] == "yes" else 0.0,
                })

    if not filas:
        print("Sin datos suficientes todavía.")
        return
    informe(filas)


def brier(xs):
    return statistics.fmean(xs)


def operaciones(filas, umbral):
    ops = []
    for f in filas:
        ask_no = 1 - f["bid"]
        e_yes = f["p"] - f["ask"] - fee(f["ask"])
        e_no = (1 - f["p"]) - ask_no - fee(ask_no)
        if e_yes >= umbral and e_yes >= e_no:
            ops.append(dict(f, lado="YES", coste=f["ask"],
                            pnl=f["y"] - f["ask"] - fee(f["ask"])))
        elif e_no >= umbral:
            ops.append(dict(f, lado="NO", coste=ask_no,
                            pnl=(1 - f["y"]) - ask_no - fee(ask_no)))
    return ops


def t_stat(xs):
    if len(xs) < 2:
        return 0.0
    s = statistics.stdev(xs)
    return statistics.fmean(xs) / (s / math.sqrt(len(xs))) if s else 0.0


def bootstrap_dias(ops, n=2000, seed=1):
    """Intervalo 90% del PnL medio remuestreando DÍAS (las apuestas de un día están correlacionadas)."""
    por_dia = defaultdict(list)
    for o in ops:
        por_dia[(o["ciudad"], o["dia"])].append(o["pnl"])
    dias = list(por_dia.values())
    rng = random.Random(seed)
    medias = []
    for _ in range(n):
        muestra = [x for _ in dias for x in rng.choice(dias)]
        medias.append(statistics.fmean(muestra))
    medias.sort()
    return medias[int(0.05 * n)], medias[int(0.95 * n)]


def calibracion(filas):
    """¿Los precios del mercado aciertan por sí solos? (no usa ninguna previsión)"""
    fs = [f for f in filas if f["decision"] == "A_vispera"]
    print(f"\n{'=' * 78}\nCALIBRACIÓN DEL MERCADO (víspera, {len(fs)} tramos)")
    print(f"{'precio YES':>12} {'n':>6} {'gana de verdad':>15} {'compra YES (PnL/contr)':>24} {'compra NO (PnL/contr)':>23}")
    cortes = [0, .03, .06, .10, .15, .25, .40, .60, .75, .85, .92, 1.01]
    for lo, hi in zip(cortes, cortes[1:]):
        b = [f for f in fs if lo <= (f["bid"] + f["ask"]) / 2 < hi]
        if len(b) < 20:
            continue
        freq = statistics.fmean(f["y"] for f in b)
        yes = statistics.fmean(f["y"] - f["ask"] - fee(f["ask"]) for f in b)
        no = statistics.fmean((1 - f["y"]) - (1 - f["bid"]) - fee(1 - f["bid"]) for f in b)
        print(f"{lo:>5.2f}-{hi:<5.2f} {len(b):>6} {freq:>15.1%} {yes:>+24.4f} {no:>+23.4f}")


def informe(filas):
    calibracion(filas)
    for dec in DECISIONES:
        fs = [f for f in filas if f["decision"] == dec]
        if not fs:
            continue
        dias = sorted({f["dia"] for f in fs})
        print(f"\n{'=' * 78}\nDECISIÓN {dec}: {len(fs)} tramos, {len(dias)} días "
              f"({dias[0]} → {dias[-1]})")
        b_mod = brier([(f["p"] - f["y"]) ** 2 for f in fs])
        b_mkt = brier([((f["bid"] + f["ask"]) / 2 - f["y"]) ** 2 for f in fs])
        print(f"Precisión (Brier, menor = mejor): modelo {b_mod:.4f} | mercado {b_mkt:.4f}")

        print(f"{'umbral':>7} {'ops':>6} {'acierto':>8} {'PnL/contrato':>13} "
              f"{'ROI':>7} {'t':>6} {'IC90% PnL/contr.':>20}")
        for u in (0.03, 0.05, 0.08, 0.10, 0.15, 0.20):
            ops = operaciones(fs, u)
            if len(ops) < 10:
                continue
            pn = [o["pnl"] for o in ops]
            gan = sum(1 for o in ops if o["pnl"] > 0) / len(ops)
            roi = sum(pn) / sum(o["coste"] + fee(o["coste"]) for o in ops)
            lo, hi = bootstrap_dias(ops)
            print(f"{u:>7.2f} {len(ops):>6} {gan:>8.1%} {statistics.fmean(pn):>+13.4f} "
                  f"{roi:>+7.1%} {t_stat(pn):>6.2f}   [{lo:+.4f}, {hi:+.4f}]")

        ops = operaciones(fs, 0.08)
        if ops:
            print("\nCon umbral 0.08 — por ciudad:")
            por = defaultdict(list)
            for o in ops:
                por[o["ciudad"]].append(o["pnl"])
            for c, pn in sorted(por.items()):
                print(f"  {c:<11} ops={len(pn):>5}  PnL/contr={statistics.fmean(pn):+.4f}  total={sum(pn):+8.2f}")
            print("Por mes:")
            por = defaultdict(list)
            for o in ops:
                por[o["dia"][:7]].append(o["pnl"])
            for mth, pn in sorted(por.items()):
                print(f"  {mth}  ops={len(pn):>5}  PnL/contr={statistics.fmean(pn):+.4f}  total={sum(pn):+8.2f}")
            por = defaultdict(list)
            for o in ops:
                por[o["lado"]].append(o["pnl"])
            print("Por lado:", {k: (len(v), round(statistics.fmean(v), 4)) for k, v in por.items()})
            vols = sorted(o["vol"] for o in ops)
            print(f"Volumen negociado en la hora de entrada (mediana): {vols[len(vols) // 2]:.0f} contratos")


if __name__ == "__main__":
    main()
