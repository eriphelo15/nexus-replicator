"""Controles posteriores: qué fue de cada token a los 30 min, 1 h, 6 h y 24 h."""

from datetime import datetime, timedelta, timezone

from . import fuentes

HORIZONTES = {"30m": 30, "1h": 60, "6h": 360, "24h": 1440, "3d": 4320, "7d": 10080}

# Un control tomado demasiado tarde ya no mide su horizonte: se marca como perdido.
# Los de 24 h y 7 d no se pierden nunca porque su precio sale de las velas.
TOLERANCIA_MIN = {"30m": 15, "1h": 20, "6h": 60, "3d": 240}

# Un token se da por muerto si su precio cae a un 10% o menos del de detección.
# (La liquidez no sirve: GeckoTerminal la da como 0 en algunos pools vivos.)
UMBRAL_MUERTO = 0.1

# Regla de salida del plan: vender 50% a 2x, 20% a 5x, 20% a 10x, dejar 10%;
# salir de todo lo que quede si cae a -50% desde la entrada.
ESCALONES = [(2.0, 0.5), (5.0, 0.2), (10.0, 0.2)]
STOP = 0.5

# Regla de tendencia, pensada para no cortar las subidas grandes: vender un
# tercio a 3x (se recupera lo invertido) y dejar correr el resto con un stop
# móvil del 50% desde el máximo. Sin stop antes de llegar a 3x.
TENDENCIA_OBJETIVO = 3.0
TENDENCIA_VENTA = 1 / 3
TENDENCIA_STOP_MOVIL = 0.5

# Máximo de tokens con velas por ejecución, por el límite de GeckoTerminal.
MAX_VELAS_POR_RONDA = 20


def simular_regla(entrada, velas, vivo_al_final):
    """Multiplicador del capital a 24 h aplicando la regla de salida.

    Dentro de una misma vela no se sabe qué llegó antes, así que se asume
    lo peor: el stop se evalúa antes que los objetivos, y se ejecuta al peor
    precio entre el stop y el cierre de la vela (en un rug pull el precio se
    desploma en una sola vela y nadie vende a -50%).
    """
    restante, realizado = 1.0, 0.0
    alcanzados = set()
    for _, _, alto, bajo, cierre, _ in velas:
        if bajo <= entrada * STOP:
            return realizado + restante * min(STOP, cierre / entrada)
        for nivel, fraccion in ESCALONES:
            if nivel not in alcanzados and alto >= entrada * nivel:
                vendido = min(fraccion, restante)
                realizado += vendido * nivel
                restante -= vendido
                alcanzados.add(nivel)
    if not vivo_al_final or not velas:
        return realizado
    return realizado + restante * velas[-1][4] / entrada


def simular_tendencia(entrada, velas, vivo_al_final):
    """Multiplicador del capital con la regla de tendencia.

    El máximo se actualiza después de evaluar el stop de cada vela y el stop
    se ejecuta al peor precio entre el nivel y el cierre (supuestos prudentes).
    """
    restante, realizado = 1.0, 0.0
    maximo, asegurado = entrada, False
    for _, _, alto, bajo, cierre, _ in velas:
        if asegurado and bajo <= maximo * TENDENCIA_STOP_MOVIL:
            return realizado + restante * min(maximo * TENDENCIA_STOP_MOVIL, cierre) / entrada
        if not asegurado and alto >= entrada * TENDENCIA_OBJETIVO:
            realizado += TENDENCIA_VENTA * TENDENCIA_OBJETIVO
            restante -= TENDENCIA_VENTA
            asegurado = True
        maximo = max(maximo, alto)
    if not vivo_al_final or not velas:
        return realizado
    return realizado + restante * velas[-1][4] / entrada


def _velas_combinadas(det, estado_actual, descargar, fin):
    """Velas desde la detección hasta `fin`, juntando el pool original y el
    actual si el token migró de pool (p. ej. pump.fun -> PumpSwap).

    Devuelve None si alguna descarga falló, para aplazar el control.
    """
    det_ts = datetime.fromisoformat(det["ts"]).timestamp()
    pools = [det["pool"]]
    if estado_actual and estado_actual.get("pool") and estado_actual["pool"] != det["pool"]:
        pools.append(estado_actual["pool"])
    por_ts = {}
    for pool in pools:
        velas = descargar(pool, fin)
        if velas is None:
            return None
        for v in velas:
            if det_ts <= v[0] < fin and (v[0] not in por_ts or v[5] > por_ts[v[0]][5]):
                por_ts[v[0]] = v
    return [por_ts[t] for t in sorted(por_ts)]


def _analizar_7d(det, estado_actual):
    det_ts = datetime.fromisoformat(det["ts"]).timestamp()
    fin = det_ts + HORIZONTES["7d"] * 60
    velas = _velas_combinadas(det, estado_actual, fuentes.velas_1h, fin)
    if velas is None:
        return None
    entrada = float(det["precio"])
    vivo = _vivo(det, estado_actual)
    if not velas or entrada <= 0:
        return {"max_x_7d": "", "horas_hasta_max_7d": "",
                "regla_tendencia_x": 0.0 if not vivo else "", "precio_7d": None}
    vela_max = max(velas, key=lambda v: v[2])
    return {
        "max_x_7d": round(vela_max[2] / entrada, 4),
        "horas_hasta_max_7d": round((vela_max[0] - det_ts) / 3600, 1),
        "regla_tendencia_x": round(simular_tendencia(entrada, velas, vivo), 4),
        "precio_7d": velas[-1][4] if vivo else 0.0,
    }


def _analizar_velas(det, estado_actual):
    det_ts = datetime.fromisoformat(det["ts"]).timestamp()
    fin = det_ts + HORIZONTES["24h"] * 60
    velas = _velas_combinadas(det, estado_actual, fuentes.velas_5m, fin)
    if velas is None:
        return None

    entrada = float(det["precio"])
    vivo = _vivo(det, estado_actual)
    if not velas or entrada <= 0:
        return {"max_x": "", "min_x": "", "min_hasta_max": "", "toco_2x": "",
                "regla_x": 0.0 if not vivo else "", "precio_24h": None}

    vela_max = max(velas, key=lambda v: v[2])
    max_x = vela_max[2] / entrada
    return {
        "max_x": round(max_x, 4),
        "min_x": round(min(v[3] for v in velas) / entrada, 4),
        "min_hasta_max": round((vela_max[0] - det_ts) / 60),
        "toco_2x": int(max_x >= 2),
        "regla_x": round(simular_regla(entrada, velas, vivo), 4),
        "precio_24h": velas[-1][4] if vivo else 0.0,
    }


# Liquidez por debajo de la cual no se puede vender: cuando retiran la liquidez
# de un pool el precio se queda congelado y parecería vivo (le pasó a C DOG,
# ROGLOVE y la mitad de las primeras alertas del vigía).
LIQ_MINIMA = 1_000


def _vivo(det, e):
    return (bool(e) and e["precio"] > UMBRAL_MUERTO * float(det["precio"])
            and e["liq"] >= LIQ_MINIMA)


def seguir(almacen, log=print):
    ahora = datetime.now(timezone.utc)
    hechos = {(s["mint"], s["horizonte"]) for s in almacen.seguimientos()}

    pendientes = []
    for d in almacen.registros():
        det_ts = datetime.fromisoformat(d["ts"])
        for h, minutos in HORIZONTES.items():
            objetivo = det_ts + timedelta(minutes=minutos)
            if (d["mint"], h) not in hechos and ahora >= objetivo:
                pendientes.append((d, h, (ahora - objetivo).total_seconds() / 60))
    if not pendientes:
        log("[seguimiento] nada pendiente")
        return []

    estado, consultados = fuentes.estado_tokens({d["mint"] for d, _, _ in pendientes})
    filas, velas_usadas, aplazados = [], 0, 0
    for d, h, retraso in pendientes:
        if d["mint"] not in consultados:
            aplazados += 1  # la API no respondió: mejor esperar que darlo por muerto
            continue
        e = estado.get(d["mint"])
        vivo = _vivo(d, e)
        fila = {"mint": d["mint"], "horizonte": h, "ts": ahora.isoformat(timespec="seconds"),
                "retraso_min": round(retraso, 1), "vivo": int(vivo),
                # Muerto = no se puede vender: vale 0 aunque el precio se haya congelado alto.
                "precio": e["precio"] if vivo else 0.0,
                "mc": e["mc"] if e else 0, "liq": e["liq"] if e else 0}

        if h in ("24h", "7d"):
            if velas_usadas >= MAX_VELAS_POR_RONDA or fuentes.sin_tiempo():
                aplazados += 1
                continue
            velas_usadas += 1
            extra = _analizar_velas(d, e) if h == "24h" else _analizar_7d(d, e)
            if extra is None:
                aplazados += 1
                continue
            precio_exacto = extra.pop("precio_24h" if h == "24h" else "precio_7d")
            if precio_exacto is not None:
                fila["precio"] = precio_exacto  # precio al cumplirse el horizonte, no el de ahora
            fila.update(extra)
        elif retraso > TOLERANCIA_MIN[h]:
            fila.update({"precio": "", "mc": "", "liq": "", "vivo": ""})  # perdido
        filas.append(fila)

    almacen.guardar_seguimientos(filas)
    log(f"[seguimiento] controles={len(filas)} aplazados={aplazados}")
    return filas


# Serie de 5 min: cuánto tiempo seguir a cada token tras detectarlo.
HORAS_SERIE = 12


def fotografiar(almacen, log=print):
    """Guarda una foto (precio, liquidez, compras/ventas de 5 min) de cada token
    detectado en las últimas HORAS_SERIE horas que siga vivo."""
    ahora = datetime.now(timezone.utc)
    ultimo_precio, ultima_liq = {}, {}
    for f in almacen.serie():
        ultimo_precio[f["mint"]] = float(f["precio"] or 0)
        ultima_liq[f["mint"]] = float(f["liq"] or 0)
    pools = {}
    for d in almacen.registros():
        if ahora - datetime.fromisoformat(d["ts"]) > timedelta(hours=HORAS_SERIE):
            continue
        previo = ultimo_precio.get(d["mint"])
        if previo is not None and (previo <= UMBRAL_MUERTO * float(d["precio"])
                                   or ultima_liq[d["mint"]] < LIQ_MINIMA):
            continue  # ya murió (precio hundido o sin liquidez): no hace falta seguir fotografiándolo
        pools[d["pool"]] = d["mint"]
    if not pools:
        return []
    estado = fuentes.pools_multi(pools)
    ts = ahora.isoformat(timespec="seconds")
    filas = [dict(e, ts=ts, mint=pools[pool]) for pool, e in estado.items() if pool in pools]
    almacen.guardar_serie(filas)
    log(f"[serie] fotos={len(filas)} de {len(pools)} tokens seguidos")
    return filas
