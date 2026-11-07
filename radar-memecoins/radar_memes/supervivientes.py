"""Supervivientes: tokens de días o semanas que siguen vivos y vuelven a despertar.

El estudio de gigantes (ESTUDIO_GIGANTES.md) encontró que los que suben rápido
en sus primeras horas casi siempre marcan su máximo el primer día y acaban en
cero, mientras que los que más valor conservan (ANSEM, GOLD, MANIFEST...)
tardaron semanas en despegar, a menudo tras "morir" y resucitar. Este escáner
busca ese segundo tipo: tokens de 3 a 120 días con volumen real que se
reactivan, y descarta los gigantes caídos que rebotan (ninguno de los que cayó
un 50% desde su máximo lo recuperó, 0 de 111).

Criterios v1: hipótesis a validar. Cada candidato se registra (avisado o
vetado) y se sigue como cualquier detección, así que el informe mide si
funcionan.
"""

from datetime import datetime, timezone

from . import escaner, fuentes, narrativas, vigia

# Cada cuánto se busca (los datos diarios no cambian más rápido).
CADA_MIN = 60
# Páginas de pools por volumen de 24 h y en tendencia de 1 h/6 h/24 h (~20 consultas).
PAGINAS_VOLUMEN = 5
PAGINAS_TENDENCIA = 5
# Candidatos a los que se descargan velas diarias, holders y RugCheck por búsqueda.
MAX_CANDIDATOS = 10
MAX_AVISOS = 3

CRITERIOS = {
    "dias_min": 3, "dias_max": 120,
    "mc_min": 300_000, "mc_max": 30_000_000,
    # Volumen de 24 h / capitalización: por debajo de 0.1 la capitalización es de
    # un pool montado a mano (10 de 40 "gigantes" del estudio eran así).
    "rotacion_min": 0.3, "rotacion_max": 10.0,
    "liq_min": 30_000, "liq_mc_min": 0.03,
    # Despertar: sube en 24 h y buena parte del volumen del día es de las últimas 6 h.
    "var_h24_min": 30.0, "vol_h6_fraccion_min": 0.4,
    "compradores_h24_min": 300, "ratio_h24_min": 1.0,
    # Precio actual frente al máximo previo (cierres diarios): un gigante caído
    # que rebota no vuelve a su máximo.
    "vs_maximo_min": 0.5,
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fila(pool, ahora):
    r = escaner._fila(pool, ahora)
    if not r:
        return None
    a = pool["attributes"]
    t24 = a["transactions"].get("h24") or {}
    r.update({
        "compradores_h24": t24.get("buyers") or 0,
        "vendedores_h24": t24.get("sellers") or 0,
        "vol_h6": _f(a["volume_usd"].get("h6")),
        "vol_h24": _f(a["volume_usd"].get("h24")),
        "var_h24": _f(a["price_change_percentage"].get("h24")),
    })
    return r


def motivos_mercado(r):
    """Criterios que se pueden comprobar con los datos del pool (sin velas)."""
    c, m = CRITERIOS, []
    if not c["mc_min"] <= r["mc"] <= c["mc_max"]:
        m.append("mc_fuera_rango")
    rot = r["vol_h24"] / r["mc"] if r["mc"] else 0
    if not c["rotacion_min"] <= rot <= c["rotacion_max"]:
        m.append("rotacion_anomala")
    if r["liq"] < c["liq_min"] or (r["mc"] and r["liq"] / r["mc"] < c["liq_mc_min"]):
        m.append("poca_liquidez")
    if r["var_h24"] < c["var_h24_min"]:
        m.append("no_despierta")
    if r["vol_h24"] and r["vol_h6"] / r["vol_h24"] < c["vol_h6_fraccion_min"]:
        m.append("volumen_no_acelera")
    if r["compradores_h24"] < c["compradores_h24_min"]:
        m.append("pocos_compradores")
    if r["compradores_h24"] / max(1, r["vendedores_h24"]) < c["ratio_h24_min"]:
        m.append("presion_venta")
    if r["edad_min"] < c["dias_min"] * 1440:
        m.append("muy_nuevo")  # edad del pool: se afina después con las velas diarias
    return m


def historia(velas):
    """Rasgos de la vida del token a partir de sus velas diarias (cierres)."""
    cierres = [v[4] for v in velas if v[4] > 0 and v[5] >= 200]
    if len(cierres) < 2:
        return None
    previo = max(cierres[:-1])
    # Peor caída antes de hoy: murió (-60% o más) y siguió vivo.
    pico, peor = 0.0, 0.0
    for p in cierres[:-1]:
        pico = max(pico, p)
        peor = max(peor, 1 - p / pico)
    return {
        "dias_vida": round((velas[-1][0] - velas[0][0]) / 86400) + 1,
        "vs_maximo": round(cierres[-1] / previo, 3),
        "peor_caida_previa": round(peor, 2),
        "resucitado": int(peor >= 0.6),
    }


def motivos_historia(h):
    c, m = CRITERIOS, []
    if not c["dias_min"] <= h["dias_vida"] <= c["dias_max"]:
        m.append("edad_fuera_rango")
    if h["vs_maximo"] < c["vs_maximo_min"]:
        m.append("gigante_caido")
    return m


def _mensaje(r):
    rot = r["vol_h24"] / max(1, r["mc"])
    lineas = [
        f"Cap. ${r['mc'] / 1e6:.2f}M · {r['dias_vida']} días de vida · liquidez ${r['liq'] / 1e3:.0f}K",
        f"24 h: {r['var_h24']:+.0f}% · volumen ${r['vol_h24'] / 1e6:.2f}M ({rot:.1f}x la cap.) · "
        f"{r['compradores_h24']} compradores / {r['vendedores_h24']} vendedores",
        f"Frente a su máximo previo: {r['vs_maximo']:.0%} · peor caída anterior: -{r['peor_caida_previa']:.0%}"
        + (" (resucitado)" if r["resucitado"] else ""),
    ]
    if r.get("top10_pct") not in (None, ""):
        lineas.append(f"Top 10 holders: {float(r['top10_pct']):.0f}% · holders: {r.get('holders')}")
    if r.get("narrativa"):
        lineas.append(f"Tema: {r['narrativa']}")
    lineas.append(f"Contrato: {r['mint']}")
    lineas.append("Sin validar. Salida del estudio: stop móvil del 30-40% desde el máximo; "
                  "si cae un 50% desde su techo, no suele volver.")
    return "\n".join(lineas)


def toca(almacen, ahora):
    previos = [datetime.fromisoformat(s["ts"]) for s in almacen.supervivientes_busquedas()]
    return not previos or (ahora - max(previos)).total_seconds() >= CADA_MIN * 60


def buscar(almacen, log=print):
    ahora = datetime.now(timezone.utc)
    if not toca(almacen, ahora):
        return []
    urls = [f"{fuentes.GECKO}/pools?sort=h24_volume_usd_desc&page={p}&include=dex"
            for p in range(1, PAGINAS_VOLUMEN + 1)]
    urls += [f"{fuentes.GECKO}/trending_pools?duration={d}&page={p}&include=dex"
             for d in ("1h", "6h", "24h") for p in range(1, PAGINAS_TENDENCIA + 1)]
    filas = {}
    for url in urls:
        for x in (fuentes._get(url) or {}).get("data", []):
            try:
                r = _fila(x, ahora)
            except (KeyError, TypeError, ValueError):
                continue
            if r and (r["mint"] not in filas or r["liq"] > filas[r["mint"]]["liq"]):
                filas[r["mint"]] = r
        fuentes._dormir(fuentes.PAUSA_GECKO)
    almacen.guardar_busqueda_supervivientes({"ts": ahora.isoformat(timespec="seconds"),
                                             "pools": len(filas)})

    vistos = {d["mint"] for d in almacen.registros()}
    candidatos = [r for r in filas.values() if r["mint"] not in vistos and not motivos_mercado(r)]
    candidatos.sort(key=lambda r: -r["vol_h24"])
    guardados, avisos = [], 0
    for r in candidatos[:MAX_CANDIDATOS]:
        if fuentes.sin_tiempo():
            break
        velas = fuentes.velas_dia(r["pool"], ahora.timestamp())
        h = historia(velas) if velas else None
        if not h or motivos_historia(h):
            continue  # sin historia o fuera de criterio: no se registra
        r.update(h)
        r.update(fuentes.rugcheck(r["mint"]) or {})
        r.update(fuentes.info_token(r["mint"]) or {})
        r["narrativa"] = (narrativas.clasificar(r["simbolo"])
                          or narrativas.clasificar(f"{r.get('nombre_token', '')} {r.get('descripcion', '')}"))
        # Los vetos del vigía, salvo el de liquidez/capitalización < 0.7: se sacó de
        # lanzamientos de minutos; un token de semanas en PumpSwap o Raydium suele
        # tener 0.05-0.3 y no por eso es una trampa.
        v = [x for x in vigia.vetos(r) if x != "poca_liquidez_para_su_cap"]
        r["vetos"] = "|".join(v)
        if v:
            r.update({"prioridad": "vetada", "avisado": 0})
        else:
            enviada = avisos < MAX_AVISOS and fuentes.notificar(
                f"Superviviente: {r['simbolo']} (${r['mc'] / 1e6:.1f}M)", _mensaje(r),
                f"https://dexscreener.com/solana/{r['pool']}", etiquetas="seedling")
            avisos += int(bool(enviada))
            r.update({"prioridad": "alta", "avisado": int(bool(enviada))})
        almacen.guardar_superviviente(r)
        guardados.append(r)
        log(f"[supervivientes] {r['simbolo']} {r['prioridad']} mc={r['mc']:.0f} "
            f"dias={r['dias_vida']} vs_max={r['vs_maximo']} vetos={r['vetos'] or '-'}")
    log(f"[supervivientes] pools={len(filas)} candidatos={len(candidatos)} registrados={len(guardados)}")
    return guardados
