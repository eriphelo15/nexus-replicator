"""Detección: registra los tokens nuevos que superan un mínimo de actividad."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import fuentes, narrativas

# Mínimo para registrar un token (no es el filtro de compra: se registran
# también los que no lo pasan, para poder comparar).
MINIMO = {
    "mc_min": 10_000, "mc_max": 5_000_000,
    "liq_min": 5_000, "edad_max_min": 24 * 60, "compradores_h1_min": 25,
}

# Máximo de tokens por escaneo que se consultan en RugCheck (límite 15/min) y
# en la ficha de holders de GeckoTerminal (~30/min): el ciclo cabe en 5 min.
# Bajado de 30 a 15 (y las carteras de 15 a 5) para que el ciclo quepa en 5 min
# con el escáner de supervivientes: con 30 tardaba los 9 min de plazo.
MAX_CONSULTAS_POR_ESCANEO = 15
# De ellos, a cuántos se les descargan las carteras compradoras (otra consulta).
MAX_CARTERAS_POR_ESCANEO = 5

# Palabras que no dicen nada del tema del token.
PALABRAS_VACIAS = {"coin", "token", "the", "and", "sol", "official", "pump", "fun",
                   "for", "of", "on", "inc", "new", "real", "first"}

# Filtro de compra v1: hipótesis a validar con los datos, no una verdad.
FILTRO = {
    "mc_min": 50_000, "mc_max": 1_500_000,
    "liq_mc_min": 0.08, "liq_mc_max": 0.6,
    "vol_mc_max": 3.0,
    "compradores_h1_min": 100,
    "ratio_cv_min": 1.2, "ratio_cv_max": 8.0,
    "top10_max": 35.0,  # % del suministro en los 10 mayores holders
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _simbolo(nombre):
    return nombre.split(" / ")[0].strip()


def _clave(simbolo):
    return "".join(c for c in simbolo.lower() if c.isalnum())


def _fila(pool, ahora):
    a = pool["attributes"]
    rel = pool["relationships"]
    mint = rel["base_token"]["data"]["id"].split("_", 1)[1]
    if mint in fuentes.MINTS_BASE:
        return None
    t, v, pc = a["transactions"], a["volume_usd"], a["price_change_percentage"]
    creado = datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00"))
    return {
        "ts": ahora.isoformat(timespec="seconds"),
        "mint": mint,
        "simbolo": _simbolo(a["name"]),
        "nombre": a["name"],
        "pool": a["address"],
        "dex": ((rel.get("dex") or {}).get("data") or {}).get("id", ""),
        "edad_min": round((ahora - creado).total_seconds() / 60, 1),
        "precio": _f(a.get("base_token_price_usd")),
        "mc": _f(a.get("market_cap_usd")) or _f(a.get("fdv_usd")),
        "liq": _f(a.get("reserve_in_usd")),
        "compradores_m5": t["m5"].get("buyers") or 0,
        "vendedores_m5": t["m5"].get("sellers") or 0,
        "compradores_h1": t["h1"].get("buyers") or 0,
        "vendedores_h1": t["h1"].get("sellers") or 0,
        "compras_m5": t["m5"].get("buys") or 0,
        "ventas_m5": t["m5"].get("sells") or 0,
        "compras_h1": t["h1"].get("buys") or 0,
        "ventas_h1": t["h1"].get("sells") or 0,
        "vol_m5": _f(v.get("m5")),
        "vol_h1": _f(v.get("h1")),
        "var_m5": _f(pc.get("m5")),
        "var_h1": _f(pc.get("h1")),
        "var_h6": _f(pc.get("h6")),
    }


def _palabras_utiles(simbolo):
    return {w for w in narrativas.palabras(simbolo)
            if len(w) >= 3 and w not in PALABRAS_VACIAS and not w.isdigit()}


def _supera_minimo(r):
    m = MINIMO
    return (m["mc_min"] <= r["mc"] <= m["mc_max"] and r["liq"] >= m["liq_min"]
            and r["edad_min"] <= m["edad_max_min"]
            and r["compradores_h1"] >= m["compradores_h1_min"] and r["precio"] > 0)


def evaluar_filtro(r):
    """Devuelve la lista de motivos por los que el token no pasa (vacía = pasa)."""
    f = FILTRO
    motivos = []
    # Sin respuesta de RugCheck (falla a menudo) no se descarta: el informe
    # separa esos tokens como "sin datos" para ver si importa.
    if r.get("rc_peligros") not in (None, "") and int(r["rc_peligros"]) > 0:
        motivos.append("peligro_rugcheck")
    if int(r.get("clones") or 0) > 0:
        motivos.append("nombre_clonado")
    if not f["mc_min"] <= r["mc"] <= f["mc_max"]:
        motivos.append("mc_fuera_rango")
    liq_mc = r["liq"] / r["mc"] if r["mc"] else 0
    if not f["liq_mc_min"] <= liq_mc <= f["liq_mc_max"]:
        motivos.append("liquidez_anomala")
    if r["mc"] and r["vol_h1"] / r["mc"] > f["vol_mc_max"]:
        motivos.append("volumen_inflado")
    if r["compradores_h1"] < f["compradores_h1_min"]:
        motivos.append("pocos_compradores")
    # Sin datos de holders no se descarta (igual que con RugCheck).
    if r.get("top10_pct") not in (None, "") and float(r["top10_pct"]) > f["top10_max"]:
        motivos.append("holders_concentrados")
    if "yes" in (r.get("mint_autoridad"), r.get("freeze_autoridad")):
        motivos.append("autoridad_activa")
    ratio = r["compradores_h1"] / max(1, r["vendedores_h1"])
    if ratio > f["ratio_cv_max"]:
        motivos.append("compras_desbalanceadas")
    elif ratio < f["ratio_cv_min"]:
        motivos.append("presion_venta")
    return motivos


def puntuar(r):
    """Puntuación orientativa (la del primer escaneo manual), para evaluarla."""
    ratio = r["compradores_h1"] / max(1, r["vendedores_h1"])
    rotacion = r["vol_h1"] / max(1, r["mc"])
    liq_mc = r["liq"] / max(1, r["mc"])
    s = min(ratio, 3) * 20 + min(rotacion, 2) * 15 + min(r["compradores_h1"], 600) / 20
    s += 10 if r["var_m5"] > 0 else -5
    s += 10 if 0.08 <= liq_mc <= 0.5 else -10
    s -= 40 * int(r.get("rc_peligros") or 0)
    return round(s, 1)


def escanear(almacen, con_rugcheck=True, log=print):
    ahora = datetime.now(timezone.utc)
    pools = fuentes.pools_recientes()
    filas = {}
    for p in pools:
        try:
            r = _fila(p, ahora)
        except (KeyError, TypeError, ValueError):
            continue
        if r and (r["mint"] not in filas or r["liq"] > filas[r["mint"]]["liq"]):
            filas[r["mint"]] = r

    previas = almacen.registros()
    vistos = {d["mint"] for d in previas}  # incluye los que ya alertó el vigía

    # Clones: mismo símbolo con distinto mint, en este escaneo o en las
    # detecciones de las últimas 48 h.
    limite = ahora - timedelta(hours=48)
    mints_por_simbolo = {}
    for d in previas:
        if datetime.fromisoformat(d["ts"]) >= limite:
            mints_por_simbolo.setdefault(_clave(d["simbolo"]), set()).add(d["mint"])
    for r in filas.values():
        mints_por_simbolo.setdefault(_clave(r["simbolo"]), set()).add(r["mint"])

    # Narrativas: calor = tokens del escaneo con esa narrativa (atención en
    # tiempo real); líder = el de más liquidez dentro de su narrativa.
    for r in filas.values():
        r["narrativa"] = narrativas.clasificar(r["simbolo"])
    por_narrativa = {}
    for r in filas.values():
        if r["narrativa"]:
            por_narrativa.setdefault(r["narrativa"], []).append(r)
    for grupo in por_narrativa.values():
        grupo.sort(key=lambda r: -r["liq"])
        for puesto, r in enumerate(grupo, 1):
            r["calor_narrativa"] = len(grupo)
            r["puesto_narrativa"] = puesto
    # Palabras calientes: detecta temas que no están en la lista de narrativas
    # (p. ej. un suceso viral) contando cuántos tokens del escaneo comparten palabra.
    mints_por_palabra = {}
    for r in filas.values():
        for w in _palabras_utiles(r["simbolo"]):
            mints_por_palabra.setdefault(w, set()).add(r["mint"])
    for r in filas.values():
        mejores = sorted(((len(mints_por_palabra[w]), w) for w in _palabras_utiles(r["simbolo"])),
                         reverse=True)
        r["calor_palabra"], r["palabra_caliente"] = mejores[0] if mejores else (0, "")

    hoy = ahora.date()
    for r in filas.values():
        r["catalizador"], r["dias_catalizador"] = narrativas.proximo_catalizador(r["narrativa"], hoy)

    nuevas = [r for r in filas.values() if r["mint"] not in vistos and _supera_minimo(r)]
    # Si hay más tokens nuevos que consultas disponibles, primero los de más compradores.
    nuevas.sort(key=lambda r: -r["compradores_h1"])
    consultados = nuevas[:MAX_CONSULTAS_POR_ESCANEO]
    carteras = []
    # RugCheck y GeckoTerminal tienen límites separados: RugCheck va en paralelo.
    with ThreadPoolExecutor(max_workers=1) as hilo:
        futuros = ({r["mint"]: hilo.submit(fuentes.rugcheck, r["mint"]) for r in consultados}
                   if con_rugcheck else {})
        for i, r in enumerate(consultados):
            r.update(fuentes.info_token(r["mint"]) or {})
            if not r.get("narrativa"):
                # El símbolo solo dice poco: probar con el nombre y la descripción.
                r["narrativa"] = narrativas.clasificar(
                    f"{r.get('nombre_token', '')} {r.get('descripcion', '')}")
                r["catalizador"], r["dias_catalizador"] = narrativas.proximo_catalizador(
                    r["narrativa"], ahora.date())
            if i < MAX_CARTERAS_POR_ESCANEO:
                compras = fuentes.compradores(r["pool"], r["mint"])
                r["carteras_registradas"] = len(compras)
                carteras += [dict(c, mint=r["mint"], ts_deteccion=r["ts"]) for c in compras]
        for r in nuevas:
            futuro = futuros.get(r["mint"])
            r.update((futuro.result() if futuro else None)
                     or {"rc_score": "", "rc_peligros": "", "rc_avisos": "",
                         "rc_riesgos": "", "lp_bloqueado": ""})

    for r in nuevas:
        r["clones"] = len(mints_por_simbolo.get(_clave(r["simbolo"]), set())) - 1
        motivos = evaluar_filtro(r)
        r["pasa_filtro"] = int(not motivos)
        r["motivo_descarte"] = "|".join(motivos)
        r["puntuacion"] = puntuar(r)

    almacen.guardar_detecciones(nuevas)
    almacen.guardar_carteras(carteras)
    log(f"[escaneo] pools={len(pools)} tokens={len(filas)} nuevos_registrados={len(nuevas)} "
        f"pasan_filtro={sum(r['pasa_filtro'] for r in nuevas)}")
    return nuevas
