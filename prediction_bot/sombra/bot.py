"""Bot en SOMBRA (sin dinero) para los mercados de temperatura máxima de Polymarket.

Cada hora a las hh:10 UTC (igual que en la simulación):
  1. calcula la probabilidad de cada tramo (modelo.py) con los datos publicados hasta ese momento
  2. si la probabilidad de un tramo cambia ≥ UMBRAL respecto a la hora anterior → "compra en papel"
     al precio REAL de venta del libro de órdenes en ese instante (no al precio histórico)
  3. cuando el mercado se resuelve, calcula la ganancia o pérdida
Genera una página web con los resultados (web.py).

    python bot.py            # bucle continuo (servicio)
    python bot.py --ronda    # una ronda ahora mismo (prueba)
"""
import gzip, json, os, sys, time, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fuentes as fu
import modelo as mo
import web

DATA = Path(os.environ.get("BOT_DATA", Path(__file__).parent / "datos"))
DATA.mkdir(parents=True, exist_ok=True)
UMBRALES = (0.15, 0.20, 0.30)
APUESTA, COMISION, PMIN, PMAX = 25.0, 0.017, 0.05, 0.95
SUMA = (0.9, 1.15)


def log(*a):
    print(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def cargar(nombre, defecto):
    p = DATA / nombre
    try:
        return json.loads(p.read_text()) if p.exists() else defecto
    except Exception:
        return defecto


def guardar(nombre, obj):
    tmp = DATA / (nombre + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(DATA / nombre)


def anotar(nombre, fila):
    with open(DATA / nombre, "a") as fh:
        fh.write(json.dumps(fila) + "\n")


def leer_ops():
    p = DATA / "operaciones.jsonl"
    return [json.loads(l) for l in open(p)] if p.exists() else []


# ------------------------------------------------------------------ datos
def preparar_datos(nwp, metar):
    if len(metar) < len(fu.EST) * 0.8 or not cargar("metar_ok", False):
        log("descargando historial METAR (IEM)…")
        fu.fusionar_metar(metar, fu.metar_historico(40))
        guardar("metar.json", metar); guardar("metar_ok", True)
    n = fu.actualizar_nwp(nwp, dias=35, log=log)
    if n:
        guardar("nwp.json", nwp)
    fu.fusionar_metar(metar, fu.metar_reciente(6))
    guardar("metar.json", metar)


# ------------------------------------------------------------------ ronda horaria
def ronda(t, nwp, metar, estado):
    ciudades = {c: mo.Ciudad(e, metar.get(c, []), nwp, c) for c, e in fu.EST.items()}
    ops = leer_ops()
    hechas = {(o["clave"], o["umbral"]) for o in ops}
    nuevas, registro = 0, []
    for c, ciu in ciudades.items():
        hoy = datetime.fromtimestamp(t, ciu.tz).date()
        for d in (hoy, hoy + timedelta(days=1)):
            ds = d.isoformat()
            if ciu.fase(ds, t) is None:
                continue
            ev = fu.evento(c, d)
            if not ev:
                continue
            tramos = [(mo.tramo(x["q"]), x) for x in ev["tramos"] if not x["cerrado"]]
            if not tramos:
                continue
            fase, r = ciu.probabilidades(ds, t, [k for k, _ in tramos])
            if not r:
                continue
            lb = fu.libros([x[y] for _, x in tramos for y in ("si", "no")])
            filas = []
            for (lo, hi), x in tramos:
                bid, _ = fu.mejor(lb.get(x["si"]), "bids")
                ask, dep_si = fu.mejor(lb.get(x["si"]), "asks")
                ask_no, dep_no = fu.mejor(lb.get(x["no"]), "asks")
                # precio de referencia: punto medio del libro si es estrecho; si no, el que muestra Polymarket
                if bid is not None and ask is not None and ask - bid <= 0.10:
                    medio = (bid + ask) / 2
                else:
                    medio = x["resultado"][0] if x.get("resultado") else None
                filas.append(dict(lo=lo, hi=hi, q=x["q"], p=r["p"][(lo, hi)], medio=medio, ask=ask, ask_no=ask_no,
                                  dep_si=dep_si, dep_no=dep_no))
            suma = sum(f["medio"] for f in filas if f["medio"] is not None)
            vivo = all(f["medio"] is not None for f in filas) and SUMA[0] <= suma <= SUMA[1]
            for f in filas:
                clave = f"{c}|{ds}|{f['lo']}"
                prev = estado.get(clave)
                dp = f["p"] - prev["p"] if prev and prev["fase"] == fase + 1 else None
                registro.append(dict(t=t, c=c, d=ds, fase=fase, lo=f["lo"], p=round(f["p"], 4), medio=f["medio"],
                                     ask=f["ask"], ask_no=f["ask_no"], dp=None if dp is None else round(dp, 4), vivo=vivo))
                if vivo:
                    estado[clave] = dict(fase=fase, p=f["p"])
                if dp is None or not vivo or not (PMIN <= f["medio"] <= PMAX):
                    continue
                for u in UMBRALES:
                    if abs(dp) < u or (clave, u) in hechas:
                        continue
                    lado = "SI" if dp > 0 else "NO"
                    precio = f["ask"] if lado == "SI" else f["ask_no"]
                    dep = f["dep_si"] if lado == "SI" else f["dep_no"]
                    if precio is None or precio >= 0.995:
                        continue
                    op = dict(clave=clave, umbral=u, t=t, c=c, d=ds, fase=fase, q=f["q"], lo=f["lo"], hi=f["hi"],
                              lado=lado, p=round(f["p"], 4), dp=round(dp, 4), medio=f["medio"], precio=precio,
                              disponible=round(dep, 2), slug=ev["slug"])
                    anotar("operaciones.jsonl", op); hechas.add((clave, u)); nuevas += 1
                    log(f"SEÑAL u={u} {c} {ds} {f['q'][-45:]} {lado} Δp={dp:+.2f} medio={f['medio']:.3f} compra={precio}")
    with gzip.open(DATA / "registro.jsonl.gz", "at") as fh:
        for x in registro:
            fh.write(json.dumps(x) + "\n")
    lim = t - 3 * 86400
    for k in [k for k in estado if datetime.fromisoformat(k.split("|")[1]).timestamp() < lim]:
        del estado[k]
    guardar("estado.json", estado)
    log(f"ronda {datetime.fromtimestamp(t, timezone.utc):%Y-%m-%d %H:%M} → {len(registro)} tramos evaluados, {nuevas} señales")


# ------------------------------------------------------------------ resolución
def resolver():
    p = DATA / "operaciones.jsonl"
    if not p.exists():
        return
    ops, cambios, cache = leer_ops(), 0, {}
    for o in ops:
        if "gana" in o:
            continue
        e = fu.EST[o["c"]]
        fin = mo.Ciudad(e, [], {}, o["c"]).dia(o["d"])[1]
        if time.time() < fin + 2 * 3600:
            continue
        if o["slug"] not in cache:
            r = fu.pedir(f"{fu.GAMMA}/events", params={"slug": o["slug"]}, intentos=2)
            cache[o["slug"]] = r.json()[0] if r and r.json() else None
        ev = cache[o["slug"]]
        if not ev:
            continue
        for m in ev.get("markets", []):
            if m["question"] == o["q"] and m.get("closed"):
                pr = [float(x) for x in json.loads(m["outcomePrices"])]
                if max(pr) < 0.99:
                    break
                si_gana = pr[0] > 0.5
                gana = si_gana if o["lado"] == "SI" else not si_gana
                acc = APUESTA / o["precio"]
                o["gana"] = gana
                o["resultado"] = round(acc * gana - APUESTA * (1 + COMISION), 2)
                # referencia: lo que habría dado la simulación (precio medio + 2 c)
                ref = (o["medio"] if o["lado"] == "SI" else 1 - o["medio"]) + 0.02
                o["resultado_sim"] = round(APUESTA / ref * gana - APUESTA * (1 + COMISION), 2)
                cambios += 1
                break
    if cambios:
        tmp = DATA / "operaciones.jsonl.tmp"
        tmp.write_text("".join(json.dumps(o) + "\n" for o in ops))
        tmp.replace(p)
        log(f"{cambios} operaciones resueltas")


# ------------------------------------------------------------------ bucle
def main():
    nwp, metar, estado = cargar("nwp.json", {}), cargar("metar.json", {}), cargar("estado.json", {})
    if "--ronda" in sys.argv:
        preparar_datos(nwp, metar)
        t = (int(time.time()) // 3600) * 3600 + 600
        ronda(t if t <= time.time() else t - 3600, nwp, metar, estado)
        resolver(); web.generar(DATA, leer_ops())
        return
    ultima, ult_datos, ult_iem = cargar("ultima_ronda", 0), 0, time.time()
    log("bot en sombra iniciado")
    while True:
        try:
            ahora = time.time()
            t = (int(ahora) // 3600) * 3600 + 600
            if ahora - ult_datos > 600 or (ahora >= t and t > ultima):
                preparar_datos(nwp, metar); ult_datos = time.time()
            if ahora >= t and t > ultima and ahora - t < 1800:
                ronda(t, nwp, metar, estado)
                ultima = t; guardar("ultima_ronda", t)
                resolver(); web.generar(DATA, leer_ops())
            if ahora - ult_iem > 86400:                 # una vez al día, rellenar huecos con el archivo IEM
                fu.fusionar_metar(metar, fu.metar_historico(3)); guardar("metar.json", metar); ult_iem = ahora
        except Exception:
            log("ERROR", traceback.format_exc())
        time.sleep(30)


if __name__ == "__main__":
    main()
