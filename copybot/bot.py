"""Bot de copia: replica en Solana las compras y ventas de las carteras seguidas.

Uso:  python bot.py config.json
Modo "simulado" (por defecto): cotiza en Jupiter en el momento real pero no envía nada.
Modo "real": necesita la clave privada de la cartera del bot en la variable BOT_CLAVE_PRIVADA
(base58). Nunca en un archivo del repositorio.

Órdenes desde el móvil (ntfy, tema NTFY_ORDENES o <NTFY_TOPIC>-bot): "parar" (no compra más, sigue
copiando ventas), "seguir", "vender todo", "estado". Si existe NTFY_CLAVE, cada orden debe empezar por
esa clave ("<clave> parar"). En modo real, sin NTFY_CLAVE ni NTFY_TOKEN no se aceptan órdenes.
"""

import asyncio
import csv
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone

import aiohttp

from lector import USDC, leer_operacion
from solana import Avisos, Jupiter, Solana


def log(msg):
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


class Bot:
    def __init__(self, cfg, sesion):
        self.cfg = cfg
        self.sol = Solana(cfg["rpc_http"], cfg["rpc_ws"], sesion)
        self.jup = Jupiter(cfg["jupiter_url"], sesion)
        self.avisos = Avisos(os.environ.get("NTFY_TOPIC", ""), sesion,
                             tema_ordenes=os.environ.get("NTFY_ORDENES", ""), token=os.environ.get("NTFY_TOKEN", ""))
        self.clave = os.environ.get("NTFY_CLAVE", "").strip().lower()
        self.real = cfg["modo"] == "real"
        # En real, cualquiera que conozca el tema podría mandar "vender todo": hace falta clave o tema protegido.
        self.ordenes_activas = bool(self.clave or self.avisos.token) or not self.real
        self.firmante = None
        if self.real:
            from solders.keypair import Keypair
            self.firmante = Keypair.from_base58_string(os.environ["BOT_CLAVE_PRIVADA"])
        self.yo = str(self.firmante.pubkey()) if self.firmante else "simulado"
        self.ruta = cfg.get("datos", "datos_bot")
        os.makedirs(self.ruta, exist_ok=True)
        self.estado = self._cargar()
        self.vistas = set()
        self.precio_sol = None
        self.bloqueo = asyncio.Lock()

    # ---------- estado ----------
    def _cargar(self):
        f = os.path.join(self.ruta, "estado.json")
        if os.path.exists(f):
            e = json.load(open(f))
            e.setdefault("ventas_pendientes", {})
            return e
        return {"posiciones": {}, "dia": "", "realizado_dia": 0.0, "pausado": False, "ventas_pendientes": {}}

    def _guardar(self):
        f = os.path.join(self.ruta, "estado.json")
        json.dump(self.estado, open(f + ".tmp", "w"), indent=1)
        os.replace(f + ".tmp", f)

    def _registrar(self, fila):
        f = os.path.join(self.ruta, "operaciones.csv")
        nuevo = not os.path.exists(f)
        with open(f, "a", newline="") as h:
            w = csv.DictWriter(h, fieldnames=list(fila))
            if nuevo:
                w.writeheader()
            w.writerow(fila)

    def _dia(self):
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.estado["dia"] != hoy:
            self.estado.update(dia=hoy, realizado_dia=0.0)

    def expuesto(self):
        return sum(p["coste"] for p in self.estado["posiciones"].values())

    # ---------- copia ----------
    async def al_recibir(self, cartera, firma):
        if firma in self.vistas:
            return
        self.vistas.add(firma)
        tx = await self.sol.transaccion(firma)
        op = leer_operacion(tx, cartera, self.precio_sol or 0)
        if not op:
            return
        retraso = time.time() - (op["t"] or time.time())
        # Solo las compras caducan. Una venta suya se copia siempre, aunque llegue tarde:
        # si no, nos quedaríamos con un token que él ya vendió.
        if op["lado"] == "compra" and retraso > self.cfg["retraso_max_s"]:
            log(f"compra ignorada por antigua ({retraso:.0f} s): {firma[:12]}")
            return
        async with self.bloqueo:   # una operación a la vez: el estado no se pisa
            if op["lado"] == "compra":
                await self.copiar_compra(cartera, op, firma, retraso)
            else:
                await self.copiar_venta(cartera, op, firma, retraso)

    async def copiar_compra(self, cartera, op, firma, retraso):
        c, sig = self.cfg, self.cfg["carteras"][cartera]
        self._dia()
        if self.estado["pausado"]:
            return log(f"pausado: no copio la compra de {op['mint'][:8]}")
        if self.estado["realizado_dia"] <= -c["perdida_dia_max_usd"]:
            return log("límite de pérdida diaria alcanzado: no copio compras")
        usd = op["usd"] * c["capital_usd"] / sig["capital_referencia_usd"] * sig.get("peso", 1.0)
        usd = min(usd, c["max_operacion_usd"])
        pos = self.estado["posiciones"].get(op["mint"], {"tokens": 0.0, "coste": 0.0, "decimales": op["decimales"]})
        usd = min(usd, c["max_por_token_usd"] - pos["coste"], c["capital_usd"] - self.expuesto())
        if usd < c["min_operacion_usd"]:
            return log(f"compra de {op['mint'][:8]} demasiado pequeña o límites llenos (${usd:.2f})")
        q = await self.jup.cotizar(USDC, op["mint"], usd * 1e6, c.get("slippage_bps", 300))
        if not q:
            return log(f"sin cotización para {op['mint'][:8]}")
        impacto = float(q.get("priceImpactPct") or 0) * 100
        if impacto > c["impacto_max_pct"]:
            return log(f"impacto {impacto:.1f}% demasiado alto en {op['mint'][:8]}")
        tokens = int(q["outAmount"]) / 10 ** op["decimales"]
        ok, mi_firma = await self._ejecutar(q)
        if not ok:
            return
        if self.real:
            # Lo recibido de verdad = saldo en cadena − lo que ya teníamos. Si el nodo no responde o aún
            # no refleja la compra, se usa la cantidad de la cotización (sin restar nada).
            saldo = await self.sol.saldo_token(self.yo, op["mint"])
            if saldo is not None and saldo > pos["tokens"]:
                tokens = saldo - pos["tokens"]
        pos["tokens"] += tokens
        pos["coste"] += usd
        self.estado["posiciones"][op["mint"]] = pos
        self._guardar()
        self._anotar("compra", cartera, op, usd, tokens, retraso, mi_firma, firma)

    async def copiar_venta(self, cartera, op, firma, retraso, fraccion=None):
        """Vende la misma fracción que él. Devuelve True si no queda nada por hacer con esta venta."""
        pos = self.estado["posiciones"].get(op["mint"])
        if not pos or pos["tokens"] <= 0:
            return True
        if fraccion is None:
            fraccion = 1.0 if op["despues"] <= 0 or op["antes"] <= 0 else min(1.0, op["tokens"] / op["antes"])
        # Si había una venta de este token sin ejecutar, se suma a esta: queda por vender 1 − (1−a)(1−b).
        pend = self.estado["ventas_pendientes"].pop(op["mint"], None)
        intentos = pend["intentos"] if pend else 0
        if pend:
            fraccion = min(1.0, 1 - (1 - pend["fraccion"]) * (1 - fraccion))
        vender = pos["tokens"] * fraccion
        slippage = self.cfg.get("slippage_venta_bps", self.cfg.get("slippage_bps", 1000))
        q = await self.jup.cotizar(op["mint"], USDC, vender * 10 ** pos["decimales"], slippage)
        if not q:
            log(f"sin cotización para vender {op['mint'][:8]}")
            return self._venta_pendiente(op["mint"], fraccion, intentos, "sin cotización")
        usd = int(q["outAmount"]) / 1e6
        ok, mi_firma = await self._ejecutar(q)
        if not ok:
            return self._venta_pendiente(op["mint"], fraccion, intentos, "no se confirmó")
        coste = pos["coste"] * fraccion
        self._dia()
        self.estado["realizado_dia"] += usd - coste
        pos["tokens"] -= vender
        pos["coste"] -= coste
        if pos["tokens"] <= 1e-9 or fraccion >= 0.999:
            self.estado["posiciones"].pop(op["mint"], None)
        self._guardar()
        self._anotar("venta", cartera, op, usd, vender, retraso, mi_firma, firma, resultado=usd - coste)
        return True

    def _venta_pendiente(self, mint, fraccion, intentos, motivo):
        """Apunta una venta que no salió para reintentarla (cada vez más espaciada, hasta 5 min)."""
        espera = min(self.cfg.get("reintento_venta_s", 15) * 2 ** intentos, 300)
        self.estado["ventas_pendientes"][mint] = {"fraccion": fraccion, "intentos": intentos + 1,
                                                  "proximo": time.time() + espera}
        self._guardar()
        if intentos == 0:
            asyncio.create_task(self.avisos.enviar("Bot: venta pendiente",
                                                   f"No pude vender {mint[:8]}… ({motivo}). Lo reintento.", "warning"))
        return False

    async def reintentar_ventas(self):
        while True:
            await asyncio.sleep(5)
            for mint, p in list(self.estado["ventas_pendientes"].items()):
                if time.time() < p.get("proximo", 0):
                    continue
                async with self.bloqueo:
                    pos = self.estado["posiciones"].get(mint)
                    if not pos or pos["tokens"] <= 0:
                        self.estado["ventas_pendientes"].pop(mint, None)
                        self._guardar()
                        continue
                    op = {"mint": mint, "tokens": 0, "antes": pos["tokens"], "despues": 0,
                          "usd": 0.0, "decimales": pos["decimales"]}
                    # fraccion=0: copiar_venta le suma la fracción pendiente
                    if await self.copiar_venta("reintento", op, "reintento", 0, fraccion=0.0):
                        log(f"venta pendiente de {mint[:8]} hecha al intento {p['intentos'] + 1}")

    async def _ejecutar(self, cotizacion):
        if not self.real:
            return True, "simulado"
        tx_bytes = await self.jup.transaccion_swap(cotizacion, self.yo, self.cfg["prioridad_max_lamports"])
        if not tx_bytes:
            log("Jupiter no devolvió la transacción")
            return False, None
        from solders.transaction import VersionedTransaction
        tx = VersionedTransaction.from_bytes(tx_bytes)
        firmada = VersionedTransaction(tx.message, [self.firmante])
        firma = await self.sol.enviar(bytes(firmada), comprobar=self.cfg.get("comprobar_antes", True))
        if not firma or not await self.sol.confirmar(firma):
            log(f"transacción no confirmada: {firma}")
            await self.avisos.enviar("Bot: operación fallida", f"No se confirmó {firma}", "warning")
            return False, firma
        return True, firma

    def _anotar(self, lado, cartera, op, usd, tokens, retraso, mi_firma, su_firma, resultado=None):
        fila = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "modo": self.cfg["modo"], "cartera": cartera[:8], "mint": op["mint"], "lado": lado,
                "usd": round(usd, 2), "tokens": tokens, "precio": usd / tokens if tokens else 0,
                "precio_suyo": op["usd"] / op["tokens"] if op["tokens"] else 0, "usd_suyo": round(op["usd"], 2),
                "retraso_s": round(retraso, 1), "resultado": "" if resultado is None else round(resultado, 2),
                "mi_firma": mi_firma, "su_firma": su_firma}
        self._registrar(fila)
        txt = f"{lado} ${usd:.2f} de {op['mint'][:8]}… ({retraso:.1f} s tras él"
        if su_firma in ("manual", "reintento") or not fila["precio_suyo"]:
            txt += ")"
        else:
            txt += f"; precio {fila['precio'] / fila['precio_suyo'] - 1:+.1%} frente al suyo)"
        if resultado is not None:
            txt += f" · resultado {resultado:+.2f} $"
        log(txt)
        asyncio.create_task(self.avisos.enviar(f"Bot {'(simulado) ' if not self.real else ''}{lado}", txt))

    # ---------- tareas de fondo ----------
    async def actualizar_sol(self):
        while True:
            p = await self.jup.precio_sol()
            if p:
                self.precio_sol = p
            await asyncio.sleep(60)

    async def respaldo(self):
        """Por si el WebSocket pierde algo: revisa las últimas firmas de cada cartera."""
        while True:
            await asyncio.sleep(self.cfg["respaldo_s"])
            for c in self.cfg["carteras"]:
                r = await self.sol.rpc("getSignaturesForAddress", [c, {"limit": 15, "commitment": "confirmed"}])
                for s in reversed(r or []):
                    if not s.get("err") and s["signature"] not in self.vistas:
                        asyncio.create_task(self.al_recibir(c, s["signature"]))

    async def ordenes(self):
        if not self.ordenes_activas:
            return log("órdenes desde el móvil DESACTIVADAS: en modo real hace falta NTFY_CLAVE o NTFY_TOKEN")
        await self.avisos.ordenes()   # descarta las órdenes antiguas al arrancar
        while True:
            await asyncio.sleep(15)
            for o in await self.avisos.ordenes():
                o = self._autorizada(o)
                if o is None:
                    continue
                if o == "parar":
                    self.estado["pausado"] = True
                elif o == "seguir":
                    self.estado["pausado"] = False
                elif o == "vender todo":
                    async with self.bloqueo:
                        for mint, p in list(self.estado["posiciones"].items()):
                            op = {"mint": mint, "tokens": p["tokens"], "antes": p["tokens"], "despues": 0,
                                  "usd": 0.0001, "decimales": p["decimales"]}
                            await self.copiar_venta("manual", op, "manual", 0, fraccion=1.0)
                    self.estado["pausado"] = True
                elif o != "estado":
                    continue
                self._guardar()
                pos = self.estado["posiciones"]
                await self.avisos.enviar("Bot: estado", f"{'PAUSADO' if self.estado['pausado'] else 'activo'} · "
                                         f"{len(pos)} posiciones · expuesto ${self.expuesto():.0f} · "
                                         f"resultado hoy {self.estado['realizado_dia']:+.2f} $ · "
                                         f"ventas pendientes {len(self.estado['ventas_pendientes'])}")

    def _autorizada(self, texto):
        """Devuelve la orden sin la clave, o None si falta la clave o no coincide."""
        if not self.clave:
            return texto
        clave, _, orden = texto.partition(" ")
        if not hmac.compare_digest(clave.encode(), self.clave.encode()):
            log("orden ignorada: clave incorrecta")
            return None
        return orden.strip()

    async def correr(self):
        log(f"modo {self.cfg['modo']} · cartera del bot {self.yo} · capital ${self.cfg['capital_usd']}")
        while self.precio_sol is None:
            self.precio_sol = await self.jup.precio_sol()
            if self.precio_sol is None:
                await asyncio.sleep(5)
        # Las firmas que ya existían al arrancar no se copian.
        for c in self.cfg["carteras"]:
            for s in await self.sol.rpc("getSignaturesForAddress", [c, {"limit": 50}]) or []:
                self.vistas.add(s["signature"])
        await asyncio.gather(self.sol.escuchar(list(self.cfg["carteras"]), self.al_recibir, log),
                             self.actualizar_sol(), self.respaldo(), self.ordenes(), self.reintentar_ventas())


async def main(ruta):
    cfg = json.load(open(ruta))
    async with aiohttp.ClientSession(headers={"User-Agent": "copybot"}) as s:
        await Bot(cfg, s).correr()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "config.json"))
