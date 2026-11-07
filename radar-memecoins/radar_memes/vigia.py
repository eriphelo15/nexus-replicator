"""Vigía: detecta tokens con tracción en sus primeros minutos y avisa al móvil.

Cada minuto lee los pools recién creados (GeckoTerminal los muestra a los
pocos segundos) y vuelve a mirar, hasta sus 15 minutos de vida, los que ya
muestran algo de actividad. Cuando uno cumple los criterios tempranos se
comprueba en RugCheck y en la ficha de holders; si no hay vetos, se guarda
en alertas.csv y se envía la notificación. El ciclo principal hace después
el seguimiento de las alertas como el de cualquier detección, así que el
informe mide si las alertas aciertan.
"""

import time
from datetime import datetime, timedelta, timezone

from . import escaner, fuentes, narrativas, salidas

EDAD_MAX_MIN = 15      # hasta qué edad se vigila un pool
PAGINAS_NUEVOS = 2     # la página 1 cubre ~1 minuto de lanzamientos

# Actividad mínima para pasar a vigilancia al verlo por primera vez.
VIGILAR = {"compradores_m5": 8, "vol_m5": 500}

# Criterios tempranos v1 (sobre los últimos 5 min): hipótesis a validar.
TEMPRANO = {
    "edad_min": 2, "mc_min": 8_000, "mc_max": 400_000,
    "compradores_m5": 40, "ratio_min": 1.3, "ratio_max": 8.0,
    "ticket_min": 25.0,   # dólares por operación: por debajo huele a bots de microcompras
    "vol_m5": 4_000, "liq_min": 5_000,
}

# Riesgos de RugCheck que descartan la alerta.
RIESGOS_VETO = ("Single holder ownership", "Top 10 holders high ownership",
                "Creator history of rugged tokens", "Freeze Authority still enabled",
                "Mint Authority still enabled", "Copycat token")
TOP10_MAX = 40.0

# Solo se avisa al móvil si el token tiene un tema relevante: una de estas
# narrativas (las genéricas "animales" y "cripto" no cuentan) o una palabra que
# ya aparece en varios tokens recientes. El resto se registra en silencio para
# poder comparar.
NARRATIVAS_RELEVANTES = {"videojuegos", "ia", "politica", "elon", "celebridades",
                         "festividades", "noticias_cripto"}
PALABRA_CALIENTE_MIN = 3   # tokens distintos con la misma palabra en las últimas 3 h

# Avisar al móvil de los lanzamientos: desactivado el 2026-09-29. De las 22 primeras
# alertas con tema y sin vetos, la mediana iba -65% a la hora y ninguna llegó a 2x en
# 6 h (el estudio de gigantes apunta en la misma dirección). Se siguen registrando.
AVISAR_LANZAMIENTOS = False


def motivos_temprano(r, clon):
    """Lista de criterios que no cumple (vacía = candidato a alerta)."""
    t = TEMPRANO
    ticket = r["vol_m5"] / max(1, r["compras_m5"] + r["ventas_m5"])
    ratio = r["compradores_m5"] / max(1, r["vendedores_m5"])
    motivos = []
    if r["edad_min"] < t["edad_min"]:
        motivos.append("muy_nuevo")
    if not t["mc_min"] <= r["mc"] <= t["mc_max"]:
        motivos.append("mc_fuera_rango")
    if r["compradores_m5"] < t["compradores_m5"]:
        motivos.append("pocos_compradores")
    if not t["ratio_min"] <= ratio <= t["ratio_max"]:
        motivos.append("ratio_compradores")
    if ticket < t["ticket_min"]:
        motivos.append("microcompras")
    if r["vol_m5"] < t["vol_m5"]:
        motivos.append("poco_volumen")
    if r["liq"] < t["liq_min"]:
        motivos.append("poca_liquidez")
    if clon:
        motivos.append("nombre_clonado")
    return motivos


def vetos(r):
    riesgos = r.get("rc_riesgos") or ""
    v = [n for n in RIESGOS_VETO if n in riesgos]
    # Cualquier riesgo que RugCheck califique de peligro (p. ej. "Large Amount of
    # LP Unlocked", que tenía Neartkt antes de que le retiraran la liquidez).
    if r.get("rc_peligros") not in (None, "") and int(float(r["rc_peligros"])) > 0:
        v.append("peligro_rugcheck")
    # Más liquidez que capitalización: pool montado a mano, no un lanzamiento normal.
    if r["mc"] and r["liq"] > r["mc"]:
        v.append("liquidez_mayor_que_cap")
    # Fuera de la curva de pump.fun, poca liquidez para su capitalización significa
    # que casi todo el suministro está en pocas carteras listas para vender: las 8
    # primeras alertas así (liquidez 0.2-0.65x la capitalización) perdieron todas.
    if r.get("dex") != "pump-fun" and r["mc"] and r["liq"] / r["mc"] < 0.7:
        v.append("poca_liquidez_para_su_cap")
    # Fuera de la curva de pump.fun, la liquidez tiene dueño: si no está bloqueada,
    # quien la puso puede retirarla en cualquier momento (14 de las 17 primeras
    # alertas a las que les retiraron la liquidez tenían 0% bloqueado).
    if (r.get("dex") != "pump-fun" and r.get("lp_bloqueado") not in (None, "")
            and float(r["lp_bloqueado"]) < 50):
        v.append("liquidez_sin_bloquear")
    if r.get("top10_pct") not in (None, "") and float(r["top10_pct"]) > TOP10_MAX:
        v.append("holders_concentrados")
    if "yes" in (r.get("mint_autoridad"), r.get("freeze_autoridad")):
        v.append("autoridad_activa")
    return v


def _mensaje(r):
    ratio = r["compradores_m5"] / max(1, r["vendedores_m5"])
    ticket = r["vol_m5"] / max(1, r["compras_m5"] + r["ventas_m5"])
    lineas = [
        f"Cap. ${r['mc'] / 1e3:.0f}K · {r['edad_min']:.0f} min de vida · liquidez ${r['liq'] / 1e3:.0f}K",
        f"5 min: {r['compradores_m5']} compradores / {r['vendedores_m5']} vendedores "
        f"({ratio:.1f}x) · ticket medio ${ticket:.0f}",
    ]
    if r.get("top10_pct") not in (None, ""):
        lineas.append(f"Top 10 holders: {float(r['top10_pct']):.0f}% · holders: {r.get('holders')}")
    tema = r.get("narrativa") or "-"
    if r.get("calor_palabra", 0) >= PALABRA_CALIENTE_MIN:
        tema += f" · \"{r['palabra_caliente']}\" en {r['calor_palabra']} tokens (3 h)"
    lineas.append(f"Tema: {tema}")
    if r.get("descripcion"):
        lineas.append(f"Descripción: {r['descripcion'][:120]}")
    if r.get("twitter"):
        lineas.append(f"X: @{r['twitter']} (comprueba que sea la cuenta real)")
    lineas.append(f"Contrato: {r['mint']}")
    lineas.append("Sin validar: comprueba en RugCheck, máximo $50 y vende la mitad a 2x.")
    return "\n".join(lineas)


def vigilar(almacen, duracion_s, cada_s=60, log=print):
    fin = time.monotonic() + duracion_s
    vigilados = {}  # pool -> fecha de creación
    alertados = {a["mint"] for a in almacen.alertas()}
    log(f"[vigia] en marcha {duracion_s / 60:.0f} min; alertas previas={len(alertados)}")
    while time.monotonic() < fin:
        inicio = time.monotonic()
        ahora = datetime.now(timezone.utc)

        # 1) Pools recién creados: los que ya se mueven pasan a vigilancia.
        for p in range(1, PAGINAS_NUEVOS + 1):
            datos = fuentes._get(f"{fuentes.GECKO}/new_pools?page={p}&include=dex") or {}
            for x in datos.get("data", []):
                a = x["attributes"]
                t5 = a["transactions"]["m5"]
                if ((t5.get("buyers") or 0) >= VIGILAR["compradores_m5"]
                        or float(a["volume_usd"].get("m5") or 0) >= VIGILAR["vol_m5"]):
                    vigilados.setdefault(a["address"], a["pool_created_at"])
            fuentes._dormir(fuentes.PAUSA_GECKO)

        # 2) Olvidar los que ya pasaron la edad de vigilancia.
        limite = ahora - timedelta(minutes=EDAD_MAX_MIN)
        vigilados = {p: c for p, c in vigilados.items()
                     if datetime.fromisoformat(c.replace("Z", "+00:00")) >= limite}

        # 3) Estado actual de los vigilados y evaluación.
        filas = []
        lista = list(vigilados)
        for i in range(0, len(lista), 30):
            datos = fuentes._get(f"{fuentes.GECKO}/pools/multi/{','.join(lista[i:i + 30])}?include=dex") or {}
            for x in datos.get("data", []):
                try:
                    r = escaner._fila(x, ahora)
                except (KeyError, TypeError, ValueError):
                    continue
                if r and r["mint"] not in alertados:
                    filas.append(r)
            fuentes._dormir(fuentes.PAUSA_GECKO)

        registros = almacen.registros()
        # Los que ya registró el escaneo principal no se vuelven a alertar.
        ya_registrados = {d["mint"] for d in registros}
        filas = [r for r in filas if r["mint"] not in ya_registrados]
        dia = ahora - timedelta(hours=24)
        tres_horas = ahora - timedelta(hours=3)
        mints_por_palabra = {}
        for d in [d for d in registros if datetime.fromisoformat(d["ts"]) >= tres_horas] + filas:
            for w in escaner._palabras_utiles(f"{d['simbolo']} {d.get('nombre_token', '')}"):
                mints_por_palabra.setdefault(w, set()).add(d["mint"])
        simbolos_previos = {escaner._clave(d["simbolo"]): d["mint"] for d in registros
                            if datetime.fromisoformat(d["ts"]) >= dia}
        for r in filas:
            clave = escaner._clave(r["simbolo"])
            clon = clave in simbolos_previos and simbolos_previos[clave] != r["mint"]
            if motivos_temprano(r, clon):
                continue
            r.update(fuentes.rugcheck(r["mint"]) or {})
            r.update(fuentes.info_token(r["mint"]) or {})
            v = vetos(r)
            if v:
                # Se registra en silencio para poder medir si cada veto acierta.
                r.update({"prioridad": "vetada", "avisado": 0, "vetos": "|".join(v),
                          "narrativa": narrativas.clasificar(r["simbolo"])})
                almacen.guardar_alerta(r)
                alertados.add(r["mint"])  # no volver a evaluarlo
                log(f"[vigia] {r['simbolo']} vetado: {', '.join(v)}")
                continue
            r["narrativa"] = (narrativas.clasificar(r["simbolo"])
                              or narrativas.clasificar(f"{r.get('nombre_token', '')} {r.get('descripcion', '')}"))
            calientes = sorted(((len(mints_por_palabra.get(w, ())), w)
                                for w in escaner._palabras_utiles(f"{r['simbolo']} {r.get('nombre_token', '')}")),
                               reverse=True)
            r["calor_palabra"], r["palabra_caliente"] = calientes[0] if calientes else (0, "")
            relevante = (r["narrativa"] in NARRATIVAS_RELEVANTES
                         or r["calor_palabra"] >= PALABRA_CALIENTE_MIN)
            r["prioridad"] = "alta" if relevante else "baja"
            r["catalizador"], r["dias_catalizador"] = narrativas.proximo_catalizador(r["narrativa"], ahora.date())
            # El filtro v1 se registra también, para comparar alertas que lo pasan y que no.
            r["clones"] = 0
            motivos = escaner.evaluar_filtro(r)
            r.update({"pasa_filtro": int(not motivos), "motivo_descarte": "|".join(motivos),
                      "puntuacion": escaner.puntuar(r)})
            enviada = AVISAR_LANZAMIENTOS and relevante and fuentes.notificar(
                f"Radar: {r['simbolo']} (${r['mc'] / 1e3:.0f}K)", _mensaje(r),
                f"https://dexscreener.com/solana/{r['pool']}")
            r["avisado"] = int(bool(enviada))
            almacen.guardar_alerta(r)
            alertados.add(r["mint"])
            log(f"[vigia] ALERTA {r['prioridad']} {r['simbolo']} {r['mint']} mc={r['mc']:.0f} "
                f"tema={r['narrativa'] or r['palabra_caliente'] or '-'} notificada={enviada}")

        # Motor de salida: posiciones de la cartera (decide él si toca revisar).
        try:
            salidas.revisar(almacen.carpeta, log)
        except Exception as e:  # un fallo aquí no debe parar las alertas
            log(f"[salidas] error: {type(e).__name__}: {e}")

        espera = cada_s - (time.monotonic() - inicio)
        if espera > 0:
            time.sleep(min(espera, max(0.0, fin - time.monotonic())))
    log("[vigia] fin")
