"""Foto periódica de los premios por liquidez de Polymarket (sin dinero real).

Cada ejecución guarda, para cada mercado con premio alto que no cierra pronto:
  - premio diario y parámetros (spread máximo, tamaño mínimo)
  - precio medio y puntuación de la liquidez ya puesta (competencia)
  - cuota que se llevaría un participante nuevo con NUESTRAS acciones por lado
  - resultado de quienes tenían órdenes puestas en las operaciones de las últimas VENTANA_H horas

Se añade una línea por mercado a historial/AAAA-MM-DD.jsonl.gz. `evaluar.py` lo analiza.

    python vigilar.py
"""
import bisect
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

C = "https://clob.polymarket.com"
D = "https://data-api.polymarket.com/trades"
MIN_RATE = 50          # $/día mínimos para considerar un mercado
NUESTRAS = 500         # acciones por lado que pondría el bot
VENTANA_H = 6          # horas de operaciones a analizar en cada foto
HIST = Path(__file__).parent / "historial"


def get(url, **kw):
    for intento in range(4):
        try:
            r = requests.get(url, timeout=30, **kw)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (intento + 1))
    return None


def mercados_con_premio():
    out, cur = [], ""
    while True:
        d = get(f"{C}/rewards/markets/current", params={"next_cursor": cur} if cur else {})
        if not d:
            break
        out += d.get("data", [])
        cur = d.get("next_cursor")
        if not cur or cur == "LTE=" or not d.get("data"):
            break
    return out


def detalle(m):
    d = get(f"{C}/markets/{m['condition_id']}")
    if not d or not d.get("accepting_orders") or len(d.get("tokens") or []) != 2:
        return None
    return dict(cid=m["condition_id"], rate=m["total_daily_rate"], v=m["rewards_max_spread"] / 100,
                minsz=m["rewards_min_size"], yes=d["tokens"][0]["token_id"], no=d["tokens"][1]["token_id"],
                q=d.get("question", "")[:120], end=d.get("end_date_iso"))


def libros(tokens):
    out = {}
    for i in range(0, len(tokens), 50):
        for _ in range(3):
            try:
                r = requests.post(f"{C}/books", json=[{"token_id": t} for t in tokens[i:i + 50]], timeout=60)
                for b in r.json():
                    out[b["asset_id"]] = b
                break
            except Exception:
                time.sleep(3)
    return out


def puntuar(m, by, bn):
    bb = max(float(x["price"]) for x in by["bids"])
    ba = min(float(x["price"]) for x in by["asks"])
    mid = (bb + ba) / 2
    v, minsz = m["v"], m["minsz"]

    def score(levels, to_yes):
        tot = 0.0
        for x in levels:
            p, s = to_yes(float(x["price"])), float(x["size"])
            dist = abs(p - mid)
            if s >= minsz and dist < v:
                tot += ((v - dist) / v) ** 2 * s
        return tot
    q1 = score(by["bids"], lambda p: p) + score(bn["asks"], lambda p: 1 - p)
    q2 = score(by["asks"], lambda p: p) + score(bn["bids"], lambda p: 1 - p)
    competencia = min(q1, q2)
    d = v / 2
    nuestro = ((v - d) / v) ** 2 * NUESTRAS
    return dict(mid=mid, spread=ba - bb, competencia=competencia,
                cuota=nuestro / (competencia + nuestro), capital=NUESTRAS * (1 - 2 * d))


def resultado_makers(m, mid, ahora):
    """Suma (por acción) de lo que ganaron/perdieron los makers en las operaciones de la ventana."""
    desde = ahora - VENTANA_H * 3600
    ts, off = [], 0
    while off < 2000:
        b = get(D, params={"market": m["cid"], "limit": 500, "offset": off, "takerOnly": "true"})
        if not isinstance(b, list) or not b:
            break
        ts += b
        if b[-1]["timestamp"] < desde or len(b) < 500:
            break
        off += 500
    pts = []
    for t in ts:
        if t["timestamp"] < desde:
            continue
        p = t["price"] if t["outcomeIndex"] == 0 else 1 - t["price"]
        compra_yes = (t["side"] == "BUY") == (t["outcomeIndex"] == 0)
        pts.append((t["timestamp"], p, float(t["size"]), compra_yes))
    pts.sort()
    tiempos = [x[0] for x in pts]

    def precio_en(tq):
        if tq >= ahora:
            return mid
        i = bisect.bisect_right(tiempos, tq) - 1
        return pts[i][1] if i >= 0 else mid
    m1 = sum((1 if c else -1) * (p - precio_en(t0 + 3600)) * s for t0, p, s, c in pts)
    mn = sum((1 if c else -1) * (p - mid) * s for t0, p, s, c in pts)
    vol = sum(s for *_, s, _ in pts)
    return dict(n_trades=len(pts), vol=vol, maker_1h=m1, maker_ahora=mn)


def main():
    ahora = time.time()
    t_iso = datetime.fromtimestamp(ahora, timezone.utc).isoformat(timespec="seconds")
    todos = mercados_con_premio()
    total_diario = sum(m["total_daily_rate"] for m in todos)
    sel = [m for m in todos if m["total_daily_rate"] >= MIN_RATE]
    with ThreadPoolExecutor(8) as p:
        sel = [x for x in p.map(detalle, sel) if x]
    lb = libros([t for m in sel for t in (m["yes"], m["no"])])

    filas = []
    limite = datetime.now(timezone.utc) + timedelta(days=2)
    for m in sel:
        by, bn = lb.get(m["yes"]), lb.get(m["no"])
        if not by or not bn or not by["bids"] or not by["asks"]:
            continue
        try:
            fin_ok = m["end"] and datetime.fromisoformat(m["end"].replace("Z", "+00:00")) > limite
        except ValueError:
            fin_ok = False
        f = dict(t=t_iso, **{k: m[k] for k in ("cid", "rate", "v", "minsz", "q", "end")}, **puntuar(m, by, bn))
        f["candidato"] = bool(fin_ok and 0.15 <= f["mid"] <= 0.85)
        filas.append(f)

    cands = [f for f in filas if f["candidato"]]
    with ThreadPoolExecutor(8) as p:
        res = list(p.map(lambda f: resultado_makers(f, f["mid"], ahora), cands))
    for f, r in zip(cands, res):
        f.update(r)

    HIST.mkdir(exist_ok=True)
    path = HIST / f"{t_iso[:10]}.jsonl.gz"
    with gzip.open(path, "at") as fh:
        fh.write(json.dumps({"t": t_iso, "resumen": True, "mercados_con_premio": len(todos),
                             "premio_total_diario": total_diario, "analizados": len(filas),
                             "candidatos": len(cands)}) + "\n")
        for f in filas:
            fh.write(json.dumps(f) + "\n")
    print(f"{t_iso}: {len(todos)} mercados con premio ({total_diario:,.0f} $/día), "
          f"{len(filas)} analizados, {len(cands)} candidatos → {path.name}")


if __name__ == "__main__":
    main()
