"""Acceso a las APIs públicas: GeckoTerminal y RugCheck."""

import json
import os
import time
from collections import Counter
import urllib.error
import urllib.request
from datetime import datetime, timezone

GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
RUGCHECK = "https://api.rugcheck.xyz/v1/tokens"

CABECERAS = {"User-Agent": "Mozilla/5.0 (radar-memes)", "Accept": "application/json"}

# GeckoTerminal permite ~30 peticiones/min en su plan gratuito. El vigía corre
# en paralelo y usa ~5/min, así que cada proceso se queda en ~20/min.
PAUSA_GECKO = 3.0
# RugCheck permite 15 peticiones/min.
PAUSA_RUGCHECK = 4.1

# Mints de SOL y stablecoins: nunca son el token que nos interesa.
MINTS_BASE = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}


# Plazo global: pasado este momento, las peticiones se cortan y el ciclo
# guarda lo que tenga (en GitHub Actions el trabajo muere a los 15 min).
_plazo = None
# Errores por tipo y dominio, para el registro del ciclo.
errores = Counter()


def fijar_plazo(segundos):
    global _plazo
    _plazo = time.monotonic() + segundos if segundos else None


def sin_tiempo():
    return _plazo is not None and time.monotonic() >= _plazo


def _dormir(segundos):
    if _plazo is not None:
        segundos = min(segundos, max(0.0, _plazo - time.monotonic()))
    time.sleep(segundos)


def _get(url, reintentos=3):
    dominio = url.split("/")[2]
    for intento in range(reintentos):
        if sin_tiempo():
            errores[f"sin_tiempo {dominio}"] += 1
            return None
        try:
            peticion = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(peticion, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            errores[f"http_{e.code} {dominio}"] += 1
            if 400 <= e.code < 500 and e.code != 429:
                return None  # error del lado de la petición: reintentar no sirve
            _dormir(10 * (intento + 1) if e.code == 429 else 2 * (intento + 1))
        except Exception as e:
            errores[f"{type(e).__name__} {dominio}"] += 1
            _dormir(2 * (intento + 1))
    return None


def pools_recientes(paginas_nuevos=10, paginas_trending=2):
    """Pools nuevos y en tendencia de Solana (GeckoTerminal), sin duplicados."""
    urls = [f"{GECKO}/new_pools?page={p}&include=dex" for p in range(1, paginas_nuevos + 1)]
    urls += [f"{GECKO}/trending_pools?duration={d}&page={p}&include=dex"
             for d in ("5m", "1h") for p in range(1, paginas_trending + 1)]
    pools = {}
    for url in urls:
        datos = _get(url)
        for x in (datos or {}).get("data", []):
            pools[x["id"]] = x
        _dormir(PAUSA_GECKO)
    return list(pools.values())


def rugcheck(mint):
    """Resumen de riesgos de RugCheck, o None si no respondió."""
    datos = _get(f"{RUGCHECK}/{mint}/report/summary")
    _dormir(PAUSA_RUGCHECK)
    if not datos or "risks" not in datos:
        return None
    riesgos = datos.get("risks") or []
    return {
        "rc_score": datos.get("score_normalised"),
        "rc_peligros": sum(1 for r in riesgos if r.get("level") == "danger"),
        "rc_avisos": sum(1 for r in riesgos if r.get("level") == "warn"),
        "rc_riesgos": "|".join(r.get("name", "") for r in riesgos),
        "lp_bloqueado": datos.get("lpLockedPct"),
    }


def estado_tokens(mints):
    """Devuelve (estado, consultados).

    `consultados` son los mints cuyo lote respondió: si uno de ellos falta en
    `estado`, de verdad no tiene pools; si su lote falló, no se sabe nada.
    """
    return _estado_tokens(list(mints))


def _estado_tokens(mints):
    """Precio, market cap, liquidez y pool principal actuales, por lotes de 30.

    Usa GeckoTerminal, la misma fuente que la detección: DexScreener no indexa
    algunos pools (p. ej. ciertos de Meteora) y haría pasar por muertos a
    tokens vivos. Un mint ausente de la respuesta queda fuera del resultado.
    """
    estado, consultados = {}, set()
    for i in range(0, len(mints), 30):
        lote = mints[i:i + 30]
        datos = _get(f"{GECKO}/tokens/multi/{','.join(lote)}?include=top_pools")
        if datos is None:
            continue
        consultados.update(lote)
        for x in datos.get("data", []):
            a = x.get("attributes", {})
            pools = ((x.get("relationships") or {}).get("top_pools") or {}).get("data") or []
            estado[a.get("address")] = {
                "precio": float(a.get("price_usd") or 0),
                "mc": float(a.get("market_cap_usd") or a.get("fdv_usd") or 0),
                "liq": float(a.get("total_reserve_in_usd") or 0),
                "pool": pools[0]["id"].split("_", 1)[1] if pools else None,
            }
        _dormir(PAUSA_GECKO)
    return estado, consultados


def velas_5m(pool, hasta_ts, limite=300):
    """Velas de 5 min en USD hasta `hasta_ts`, en orden cronológico.

    Cada vela es (ts, apertura, máximo, mínimo, cierre, volumen). Devuelve
    None si la API no respondió.
    """
    return _velas(pool, hasta_ts, "minute?aggregate=5", limite)


def velas_1h(pool, hasta_ts, limite=200):
    """Velas de 1 hora en USD hasta `hasta_ts`, en orden cronológico."""
    return _velas(pool, hasta_ts, "hour?aggregate=1", limite)


def velas_dia(pool, hasta_ts, limite=180):
    """Velas diarias en USD hasta `hasta_ts` (vida del token en el pool)."""
    return _velas(pool, hasta_ts, "day?aggregate=1", limite)


def _velas(pool, hasta_ts, marco, limite):
    url = (f"{GECKO}/pools/{pool}/ohlcv/{marco}&limit={limite}"
           f"&currency=usd&before_timestamp={int(hasta_ts)}")
    datos = _get(url)
    _dormir(PAUSA_GECKO)
    if datos is None:
        return None  # la API no respondió (distinto de "no hay velas")
    lista = datos.get("data", {}).get("attributes", {}).get("ohlcv_list") or []
    return sorted(tuple(v) for v in lista)


def info_token(mint):
    """Holders y autoridades del token (GeckoTerminal), o None si no respondió.

    `top10_pct` es el % del suministro en manos de los 10 mayores holders
    según GeckoTerminal; `holders_antig_min` indica cuán reciente es el dato.
    """
    datos = _get(f"{GECKO}/tokens/{mint}/info")
    _dormir(PAUSA_GECKO)
    a = (datos or {}).get("data", {}).get("attributes")
    if not a:
        return None
    h = a.get("holders") or {}
    dist = h.get("distribution_percentage") or {}
    antig = ""
    if h.get("last_updated"):
        t = datetime.fromisoformat(h["last_updated"].replace("Z", "+00:00"))
        antig = round((datetime.now(timezone.utc) - t).total_seconds() / 60)
    return {
        "holders": h.get("count") or "",
        "top10_pct": dist.get("top_10") or "",
        "top11_20_pct": dist.get("11_20") or "",
        "holders_antig_min": antig,
        "mint_autoridad": a.get("mint_authority") or "",
        "freeze_autoridad": a.get("freeze_authority") or "",
        "gt_score": round(a["gt_score"], 1) if a.get("gt_score") is not None else "",
        "nombre_token": a.get("name") or "",
        "descripcion": " ".join((a.get("description") or "").split())[:200],
        "twitter": a.get("twitter_handle") or "",
        "web": " ".join(a.get("websites") or []),
    }


def compradores(pool, mint, minimo_usd=100, maximo=40):
    """Carteras que compraron el token en el pool (últimas ~300 operaciones).

    Devuelve hasta `maximo` carteras ordenadas por dólares comprados, con su
    primera compra. Las compras de menos de `minimo_usd` se ignoran (polvo y
    bots de volumen).
    """
    datos = _get(f"{GECKO}/pools/{pool}/trades?trade_volume_in_usd_greater_than={minimo_usd}")
    _dormir(PAUSA_GECKO)
    carteras = {}
    for t in (datos or {}).get("data", []):
        a = t.get("attributes", {})
        if a.get("kind") != "buy" or a.get("to_token_address") != mint:
            continue
        c = carteras.setdefault(a["tx_from_address"], {"usd": 0.0, "primera": a["block_timestamp"]})
        c["usd"] += float(a.get("volume_in_usd") or 0)
        c["primera"] = min(c["primera"], a["block_timestamp"])
    orden = sorted(carteras.items(), key=lambda kv: -kv[1]["usd"])[:maximo]
    return [{"cartera": k, "usd": round(v["usd"], 2), "primera_compra": v["primera"]} for k, v in orden]


def pools_multi(pools):
    """Estado actual de varios pools (lotes de 30): precio, liquidez y
    operaciones de los últimos 5 min. Los pools cuyo lote falló no aparecen."""
    estado = {}
    pools = list(pools)
    for i in range(0, len(pools), 30):
        datos = _get(f"{GECKO}/pools/multi/{','.join(pools[i:i + 30])}")
        for x in (datos or {}).get("data", []):
            a = x.get("attributes", {})
            t5 = (a.get("transactions") or {}).get("m5") or {}
            pc = a.get("price_change_percentage") or {}
            estado[a.get("address")] = {
                "precio": float(a.get("base_token_price_usd") or 0),
                "mc": float(a.get("market_cap_usd") or a.get("fdv_usd") or 0),
                "liq": float(a.get("reserve_in_usd") or 0),
                "compras_m5": t5.get("buys") or 0, "ventas_m5": t5.get("sells") or 0,
                "compradores_m5": t5.get("buyers") or 0, "vendedores_m5": t5.get("sellers") or 0,
                "vol_m5": float((a.get("volume_usd") or {}).get("m5") or 0),
                "var_m5": float(pc.get("m5") or 0), "var_h1": float(pc.get("h1") or 0),
            }
        _dormir(PAUSA_GECKO)
    return estado


def notificar(titulo, texto, enlace=None, etiquetas="rocket"):
    """Envía una notificación push por ntfy.sh al tema de NTFY_TOPIC.

    Sin NTFY_TOPIC no envía nada (devuelve False). El tema va en un secreto:
    quien lo conozca puede leer y publicar en él. Se publica en JSON para que
    los acentos y los nombres con caracteres especiales lleguen bien.
    """
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    if not tema:
        return False
    cuerpo = {"topic": tema, "title": titulo, "message": texto, "tags": [etiquetas], "priority": 4}
    if enlace:
        cuerpo["click"] = enlace
    try:
        peticion = urllib.request.Request("https://ntfy.sh/", data=json.dumps(cuerpo).encode("utf-8"),
                                          headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(peticion, timeout=15).close()
        return True
    except Exception as e:
        errores[f"{type(e).__name__} ntfy.sh"] += 1
        return False
