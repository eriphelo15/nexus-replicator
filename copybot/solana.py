"""Acceso al nodo de Solana (HTTP y WebSocket), a Jupiter y a ntfy."""

import asyncio
import base64
import json

import aiohttp
import websockets

from lector import USDC, WSOL


class Solana:
    def __init__(self, http_url, ws_url, sesion):
        self.http_url, self.ws_url, self.s = http_url, ws_url, sesion

    async def rpc(self, metodo, params, intentos=4):
        for i in range(intentos):
            try:
                async with self.s.post(self.http_url, json={"jsonrpc": "2.0", "id": 1, "method": metodo,
                                                            "params": params}, timeout=20) as r:
                    d = await r.json(content_type=None)
                if "result" in d:
                    return d["result"]
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            await asyncio.sleep(0.4 * (i + 1))
        return None

    async def transaccion(self, firma, intentos=6):
        # Recién confirmada, a veces el nodo aún no la devuelve: se reintenta.
        for i in range(intentos):
            tx = await self.rpc("getTransaction", [firma, {"encoding": "jsonParsed", "commitment": "confirmed",
                                                          "maxSupportedTransactionVersion": 1}], intentos=1)
            if tx:
                return tx
            await asyncio.sleep(0.3 * (i + 1))
        return None

    async def escuchar(self, carteras, al_recibir, log):
        """Llama a al_recibir(cartera, firma) por cada transacción nueva de las carteras."""
        espera = 1
        while True:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, max_size=None) as ws:
                    subs = {}
                    for i, c in enumerate(carteras):
                        await ws.send(json.dumps({"jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                                                  "params": [{"mentions": [c]}, {"commitment": "confirmed"}]}))
                        resp = json.loads(await ws.recv())
                        subs[resp["result"]] = c
                    log(f"escuchando {len(carteras)} cartera(s)")
                    espera = 1
                    async for msg in ws:
                        d = json.loads(msg)
                        p = d.get("params") or {}
                        v = (p.get("result") or {}).get("value") or {}
                        if v.get("signature") and not v.get("err") and p.get("subscription") in subs:
                            asyncio.create_task(al_recibir(subs[p["subscription"]], v["signature"]))
            except Exception as e:  # cualquier corte: reconectar
                log(f"conexión perdida ({type(e).__name__}); reconecto en {espera} s")
                await asyncio.sleep(espera)
                espera = min(espera * 2, 30)

    async def saldo_token(self, dueno, mint):
        r = await self.rpc("getTokenAccountsByOwner", [dueno, {"mint": mint}, {"encoding": "jsonParsed"}])
        if r is None:
            return None
        return sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for a in r["value"])

    async def enviar(self, tx_bytes, comprobar=True):
        # comprobar=True: el nodo simula la transacción antes de enviarla y la rechaza si iba a fallar
        # (p. ej. por deslizamiento), en vez de enviarla a ciegas y pagar la comisión.
        return await self.rpc("sendTransaction", [base64.b64encode(tx_bytes).decode(),
                                                  {"encoding": "base64", "skipPreflight": not comprobar,
                                                   "preflightCommitment": "confirmed", "maxRetries": 3}])

    async def confirmar(self, firma, segundos=40):
        for _ in range(segundos * 2):
            r = await self.rpc("getSignatureStatuses", [[firma]], intentos=1)
            st = (r or {}).get("value", [None])[0] if r else None
            if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
                return st.get("err") is None
            await asyncio.sleep(0.5)
        return False


class Jupiter:
    def __init__(self, url, sesion):
        self.url, self.s = url.rstrip("/"), sesion

    async def cotizar(self, entrada, salida, cantidad_atomica, slippage_bps):
        params = {"inputMint": entrada, "outputMint": salida, "amount": str(int(cantidad_atomica)),
                  "slippageBps": str(slippage_bps)}
        try:
            async with self.s.get(f"{self.url}/quote", params=params, timeout=10) as r:
                d = await r.json(content_type=None)
            return d if "outAmount" in d else None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    async def transaccion_swap(self, cotizacion, usuario, prioridad_max_lamports):
        cuerpo = {"quoteResponse": cotizacion, "userPublicKey": usuario, "wrapAndUnwrapSol": True,
                  "dynamicComputeUnitLimit": True,
                  "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {
                      "maxLamports": prioridad_max_lamports, "priorityLevel": "veryHigh"}}}
        try:
            async with self.s.post(f"{self.url}/swap", json=cuerpo, timeout=10) as r:
                d = await r.json(content_type=None)
            return base64.b64decode(d["swapTransaction"]) if "swapTransaction" in d else None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    async def precio_sol(self):
        # 1 SOL -> USDC
        q = await self.cotizar(WSOL, USDC, 10**9, 50)
        return int(q["outAmount"]) / 1e6 if q else None


class Avisos:
    """ntfy: avisos al móvil y órdenes desde el móvil (tema <tema>-bot)."""

    def __init__(self, tema, sesion, tema_ordenes="", token=""):
        self.tema, self.s, self.vistos = tema, sesion, set()
        # Tema de órdenes propio (NTFY_ORDENES) para que no se deduzca del de avisos; si no, <tema>-bot.
        self.tema_ordenes = tema_ordenes or (f"{tema}-bot" if tema else "")
        # Token de ntfy (tema reservado/protegido): sin él nadie más puede leer ni publicar.
        self.token = token
        self.cab = {"Authorization": f"Bearer {token}"} if token else {}

    async def enviar(self, titulo, texto, etiqueta="robot"):
        if not self.tema:
            return
        try:
            await self.s.post("https://ntfy.sh/", json={"topic": self.tema, "title": titulo,
                                                        "message": texto, "tags": [etiqueta]},
                              headers=self.cab, timeout=10)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass

    async def ordenes(self):
        if not self.tema_ordenes:
            return []
        try:
            async with self.s.get(f"https://ntfy.sh/{self.tema_ordenes}/json?poll=1&since=10m",
                                  headers=self.cab, timeout=10) as r:
                lineas = (await r.text()).splitlines()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return []
        nuevas = []
        for l in lineas:
            try:
                m = json.loads(l)
            except ValueError:
                continue
            if m.get("event") == "message" and m["id"] not in self.vistos:
                self.vistos.add(m["id"])
                nuevas.append(m.get("message", "").strip().lower())
        return nuevas
