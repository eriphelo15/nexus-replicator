"""Motor de salida: vigila los tokens en los que estás posicionado y avisa cuándo salir.

Le dices qué tienes publicando mensajes en el tema de ntfy `<NTFY_TOPIC>-cartera`
(desde la propia app de ntfy):

- `<contrato>` o `+<contrato>`: empezar a vigilarlo (entrada = precio de ese momento).
- `-<contrato>` o `vendí <contrato>`: dejar de vigilarlo.
- `lista`: te responde con tus posiciones y cómo van.

Reglas, sacadas del estudio de gigantes (ESTUDIO_GIGANTES.md):

- Stop móvil del 30% desde el máximo alcanzado desde tu entrada: con velas
  diarias capturaba un 54% del máximo, frente a un 3% de aguantar.
- Caída del 50% desde el máximo: ninguno de los 111 gigantes que cayeron así
  volvió a su máximo.
- Liquidez retirada (cae a la mitad o por debajo de $1,000): rug pull.
- Avisos previos, no órdenes: volumen de 24 h en récord con el precio ya
  multiplicado (el techo suele llegar ese día o poco antes) y presión de venta
  fuerte (más del doble de vendedores que compradores en 5 min y -20% en 1 h).

Cada aviso se guarda en salidas.csv con el precio y el máximo, para medir
después si salir fue acertado.
"""

import csv
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

from . import fuentes

STOP_MOVIL = 0.30
CAIDA_FINAL = 0.50
LIQ_CAIDA = 0.50
LIQ_MINIMA = 1_000
VOLUMEN_RECORD_X = 1.5      # el volumen de 24 h supera en 1.5x el mayor visto
VOLUMEN_RECORD_MIN_X = 2.0  # solo si el precio ya multiplica x2 la entrada
# Escalera: todas las variaciones de 5 min de la última media hora al alza. En la
# serie del radar precedió un desplome (caída al 40% o menos en 30 min) el 46% de
# las veces, frente al 2% sin ella; una subida de +100% en 1 h, el 13% frente al 1%.
ESCALERA_MIN = 30
SUBIDA_H1 = 100.0
PRESION_RATIO = 2.0
PRESION_VAR_H1 = -20.0
# Horas mínimas entre dos avisos del mismo tipo (los de salida se envían una vez).
REPETIR_H = {"volumen_record": 6, "presion_venta": 1, "escalera": 1, "subida_h1": 2}
CADA_S = 120  # cada cuánto revisar (se llama desde el bucle del vigía)

MINT = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
COLUMNAS = ["ts", "mint", "simbolo", "tipo", "precio", "entrada", "maximo", "x_entrada",
            "vs_maximo", "liq", "mc", "enviado"]


def _tema():
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    return f"{tema}-cartera" if tema else ""


def _ahora():
    return datetime.now(timezone.utc)


class Cartera:
    """Estado en <datos>/posiciones.json, escrito de forma atómica (el ciclo
    principal hace commit de la carpeta mientras el vigía escribe)."""

    def __init__(self, carpeta):
        self.ruta = os.path.join(carpeta, "posiciones.json")
        self.ruta_log = os.path.join(carpeta, "salidas.csv")
        self.estado = {"atendidos": [], "posiciones": {}}
        if os.path.exists(self.ruta):
            with open(self.ruta, encoding="utf-8") as f:
                self.estado = json.load(f)

    @property
    def posiciones(self):
        return self.estado["posiciones"]

    def guardar(self):
        tmp = self.ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.estado, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.ruta)

    def registrar(self, fila):
        nuevo = not os.path.exists(self.ruta_log)
        with open(self.ruta_log, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            w.writerow(fila)


def leer_mensajes(tema):
    """Mensajes publicados en el tema de la cartera en las últimas 12 h (lo que
    guarda ntfy); quien llama descarta los ya atendidos por su id."""
    url = f"https://ntfy.sh/{tema}/json?poll=1&since=12h"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=fuentes.CABECERAS),
                                    timeout=15) as r:
            lineas = r.read().decode("utf-8").splitlines()
    except Exception as e:
        fuentes.errores[f"{type(e).__name__} ntfy.sh"] += 1
        return None
    mensajes = []
    for linea in lineas:
        try:
            m = json.loads(linea)
        except ValueError:
            continue
        if m.get("event") == "message":
            mensajes.append(m)
    return sorted(mensajes, key=lambda m: m["time"])


def interpretar(texto):
    """('alta' | 'baja' | 'lista' | None, [mints])."""
    t = texto.strip()
    mints = MINT.findall(t)
    if not mints:
        return ("lista", []) if t.lower().startswith("lista") else (None, [])
    baja = t.startswith("-") or re.search(r"\b(vend|sal[ií]|quita|borra)", t.lower())
    return ("baja" if baja else "alta"), mints


def _estado(mints):
    """Precio, cap., liquidez y volumen 24 h del token, más compradores/vendedores
    de 5 min y variación de 1 h de su pool principal."""
    estado, _ = fuentes.estado_tokens(mints)
    pools = {e["pool"]: m for m, e in estado.items() if e.get("pool")}
    if pools:
        for pool, e in fuentes.pools_multi(pools).items():
            estado[pools[pool]].update({k: e[k] for k in ("compradores_m5", "vendedores_m5",
                                                          "var_m5", "var_h1")})
    return estado


def _vol24(mints):
    datos = fuentes._get(f"{fuentes.GECKO}/tokens/multi/{','.join(mints)}") or {}
    fuentes._dormir(fuentes.PAUSA_GECKO)
    return {x["attributes"]["address"]: float((x["attributes"].get("volume_usd") or {}).get("h24") or 0)
            for x in datos.get("data", [])}


def _simbolo(mint):
    datos = fuentes._get(f"{fuentes.GECKO}/tokens/{mint}") or {}
    fuentes._dormir(fuentes.PAUSA_GECKO)
    return (datos.get("data") or {}).get("attributes", {}).get("symbol") or mint[:6]


def _fmt(p):
    return f"${p:.3g}" if p < 1 else f"${p:,.2f}"


def _linea(mint, p, e):
    x = e["precio"] / p["entrada"] if p["entrada"] else 0
    return (f"{p['simbolo']}: x{x:.2f} desde tu entrada · {e['precio'] / p['maximo']:.0%} de su máximo · "
            f"cap. ${e['mc'] / 1e3:,.0f}K · liq. ${e['liq'] / 1e3:,.0f}K")


def atender_mensajes(cartera, log=print):
    tema = _tema()
    if not tema:
        return
    atendidos = cartera.estado.setdefault("atendidos", [])
    mensajes = [m for m in leer_mensajes(tema) or [] if m["id"] not in atendidos]
    if not mensajes:
        return
    ahora = _ahora()
    for m in mensajes:
        atendidos.append(m["id"])
        del atendidos[:-500]  # ntfy solo guarda 12 h: no hace falta recordar más
        orden, mints = interpretar(m.get("message", ""))
        if orden == "alta":
            estado = _estado(mints)
            for mint in mints:
                e = estado.get(mint)
                if not e or not e["precio"]:
                    fuentes.notificar("Cartera: no encuentro el token", f"Sin precio para {mint}.",
                                      etiquetas="warning")
                    continue
                simbolo = _simbolo(mint)
                cartera.posiciones[mint] = {
                    "simbolo": simbolo, "alta": ahora.isoformat(timespec="seconds"),
                    "entrada": e["precio"], "maximo": e["precio"], "liq_ref": e["liq"],
                    "vol24_max": 0.0, "avisos": {},
                }
                fuentes.notificar(f"Vigilando {simbolo}",
                                  f"Entrada {_fmt(e['precio'])} · cap. ${e['mc'] / 1e3:,.0f}K\n"
                                  f"Te aviso si cae un {STOP_MOVIL:.0%} desde su máximo, si retiran "
                                  f"liquidez o si ves señales de techo.\nContrato: {mint}",
                                  etiquetas="eyes")
                log(f"[salidas] alta {simbolo} {mint} entrada={e['precio']}")
        elif orden == "baja":
            for mint in mints:
                p = cartera.posiciones.pop(mint, None)
                if p:
                    fuentes.notificar(f"Dejo de vigilar {p['simbolo']}", f"Contrato: {mint}",
                                      etiquetas="wave")
                    log(f"[salidas] baja {p['simbolo']} {mint}")
        elif orden == "lista":
            if not cartera.posiciones:
                fuentes.notificar("Cartera vacía", "No estoy vigilando ningún token.", etiquetas="eyes")
                continue
            estado = _estado(list(cartera.posiciones))
            lineas = [_linea(mint, p, estado[mint]) if mint in estado else f"{p['simbolo']}: sin datos"
                      for mint, p in cartera.posiciones.items()]
            fuentes.notificar(f"Cartera: {len(lineas)} tokens", "\n".join(lineas), etiquetas="eyes")
    cartera.guardar()


def escalera(historial, ahora):
    """True si en los últimos ESCALERA_MIN minutos hay revisiones que los cubren
    y en todas la variación de 5 min fue positiva."""
    desde = ahora.timestamp() - ESCALERA_MIN * 60
    tramo = [v for t, v in historial if t >= desde - 60]
    cubre = historial and historial[0][0] <= desde + 60
    return bool(cubre and len(tramo) >= 5 and all(v > 0 for v in tramo))


def senales(p, e, vol24, ahora):
    """Lista de (tipo, es_salida, texto) activas para una posición."""
    s = []
    precio, maximo = e["precio"], p["maximo"]
    if e["liq"] < LIQ_MINIMA or (p["liq_ref"] and e["liq"] < LIQ_CAIDA * p["liq_ref"]):
        s.append(("liquidez_retirada", True,
                  f"La liquidez cayó a ${e['liq'] / 1e3:,.1f}K (era ${p['liq_ref'] / 1e3:,.1f}K): "
                  "pueden estar retirándola. Sal ya si todavía puedes."))
    if maximo and precio <= (1 - CAIDA_FINAL) * maximo:
        s.append(("caida_50", True,
                  f"Está a un {precio / maximo:.0%} de su máximo. Ninguno de los 111 gigantes del "
                  "estudio que cayó un 50% volvió a su máximo."))
    elif maximo and precio <= (1 - STOP_MOVIL) * maximo:
        s.append(("stop_30", True,
                  f"Cayó un {1 - precio / maximo:.0%} desde su máximo ({_fmt(maximo)}). "
                  "Stop móvil del 30%: salir."))
    if (vol24 and p.get("vol24_max") and vol24 >= VOLUMEN_RECORD_X * p["vol24_max"]
            and precio >= VOLUMEN_RECORD_MIN_X * p["entrada"]):
        s.append(("volumen_record", False,
                  f"Volumen de 24 h en récord (${vol24 / 1e6:,.2f}M) con el precio x"
                  f"{precio / p['entrada']:.1f}: el techo suele llegar ese día o poco antes. "
                  "Valora asegurar una parte."))
    actual = [[ahora.timestamp(), e["var_m5"]]] if "var_m5" in e else []
    if escalera((p.get("historial") or []) + actual, ahora):
        s.append(("escalera", False,
                  f"Lleva {ESCALERA_MIN} min subiendo sin un solo retroceso de 5 min. En los datos del "
                  "radar, casi la mitad de las escaleras (46%) acabaron en un desplome del 60% en "
                  "30 min. Asegura ganancias."))
    if e.get("var_h1", 0) >= SUBIDA_H1:
        s.append(("subida_h1", False,
                  f"+{e['var_h1']:.0f}% en 1 h: tras subidas así el desplome es 10 veces más "
                  "frecuente. Valora asegurar una parte."))
    ratio = e.get("vendedores_m5", 0) / max(1, e.get("compradores_m5", 0))
    if ratio >= PRESION_RATIO and e.get("var_h1", 0) <= PRESION_VAR_H1:
        s.append(("presion_venta", False,
                  f"{e.get('vendedores_m5')} vendedores frente a {e.get('compradores_m5')} compradores "
                  f"en 5 min y {e.get('var_h1'):.0f}% en 1 h."))
    return s


def revisar(carpeta, log=print):
    """Lee los mensajes de la cartera y revisa las posiciones. Pensado para
    llamarse desde el bucle del vigía; decide solo si toca (cada CADA_S)."""
    cartera = Cartera(carpeta)
    ahora = _ahora()
    ultima = cartera.estado.get("revisado")
    if ultima and (ahora - datetime.fromisoformat(ultima)).total_seconds() < CADA_S:
        return
    cartera.estado["revisado"] = ahora.isoformat(timespec="seconds")
    atender_mensajes(cartera, log)
    if not cartera.posiciones:
        cartera.guardar()
        return
    mints = list(cartera.posiciones)
    estado = _estado(mints)
    vol = _vol24(mints)
    for mint, p in cartera.posiciones.items():
        e = estado.get(mint)
        if not e or not e["precio"]:
            continue
        v24 = vol.get(mint, 0.0)
        for tipo, es_salida, texto in senales(p, e, v24, ahora):
            previo = p["avisos"].get(tipo)
            if previo and (es_salida or (ahora - datetime.fromisoformat(previo)).total_seconds()
                           < REPETIR_H[tipo] * 3600):
                continue
            titulo = (f"SAL YA: {p['simbolo']}" if es_salida else f"Atención: {p['simbolo']}")
            enviado = fuentes.notificar(titulo, f"{texto}\n{_linea(mint, p, e)}\nContrato: {mint}",
                                        f"https://dexscreener.com/solana/{e.get('pool') or mint}",
                                        etiquetas="rotating_light" if es_salida else "warning")
            if _tema() and not enviado:
                log(f"[salidas] no se pudo enviar {tipo} {p['simbolo']}: se reintenta")
                continue
            p["avisos"][tipo] = ahora.isoformat(timespec="seconds")
            cartera.registrar({"ts": p["avisos"][tipo], "mint": mint, "simbolo": p["simbolo"],
                               "tipo": tipo, "precio": e["precio"], "entrada": p["entrada"],
                               "maximo": p["maximo"], "x_entrada": round(e["precio"] / p["entrada"], 4),
                               "vs_maximo": round(e["precio"] / p["maximo"], 4), "liq": e["liq"],
                               "mc": e["mc"], "enviado": int(bool(enviado))})
            log(f"[salidas] {tipo} {p['simbolo']} precio={e['precio']} max={p['maximo']}")
        # El máximo y las referencias se actualizan después de evaluar las señales.
        p["maximo"] = max(p["maximo"], e["precio"])
        p["liq_ref"] = max(p["liq_ref"], e["liq"])
        p["vol24_max"] = max(p.get("vol24_max") or 0.0, v24)
        if "var_m5" in e:
            h = p.setdefault("historial", [])
            h.append([ahora.timestamp(), e["var_m5"]])
            del h[:-40]
    cartera.guardar()
