"""Pruebas del bot en modo simulado, sin red: python -m pytest copybot/test_bot.py"""
import asyncio
import json
import time

import bot as B

MINT, CART = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "CarteraSeguida"
CFG = {"modo": "simulado", "rpc_http": "", "rpc_ws": "", "jupiter_url": "http://x",
       "carteras": {CART: {"nombre": "t", "capital_referencia_usd": 10_000, "peso": 1.0}},
       "capital_usd": 1000, "min_operacion_usd": 1, "max_operacion_usd": 1000, "max_por_token_usd": 100,
       "perdida_dia_max_usd": 1000, "impacto_max_pct": 5, "slippage_bps": 300, "slippage_venta_bps": 1000,
       "retraso_max_s": 20, "respaldo_s": 20, "reintento_venta_s": 15}


class Jup:
    def __init__(self):
        self.falla = False
    async def cotizar(self, entrada, salida, cantidad, slippage):
        if self.falla:
            return None
        if entrada == B.USDC:      # 1 token = 1 USD, 6 decimales
            return {"outAmount": str(int(cantidad)), "priceImpactPct": "0"}
        return {"outAmount": str(int(cantidad)), "priceImpactPct": "0"}


class Avisos:
    token = ""
    def __init__(self):
        self.enviados = []
    async def enviar(self, *a):
        self.enviados.append(a)


def crear(tmp_path, monkeypatch, modo="simulado", env=None):
    for k in ("NTFY_TOPIC", "NTFY_CLAVE", "NTFY_TOKEN", "NTFY_ORDENES"):
        monkeypatch.delenv(k, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    cfg = dict(CFG, datos=str(tmp_path), modo="simulado")
    b = B.Bot(cfg, None)
    b.jup, b.avisos, b.precio_sol = Jup(), Avisos(), 100.0
    if modo == "real":            # sin firmar nada: solo para probar las reglas del modo real
        b.real = True
    return b


def op(lado, usd=1000.0, tokens=1000.0, antes=0.0, despues=None, hace=1):
    despues = (antes + tokens if lado == "compra" else antes - tokens) if despues is None else despues
    return {"mint": MINT, "lado": lado, "tokens": tokens, "antes": antes, "despues": despues, "decimales": 6,
            "usd": usd, "t": time.time() - hace}


def recibir(b, monkeypatch, o, firma):
    async def tx(_):
        return {}
    b.sol.transaccion = tx
    monkeypatch.setattr(B, "leer_operacion", lambda *a: o)
    async def run():
        await b.al_recibir(CART, firma)
        await asyncio.sleep(0)
    asyncio.run(run())


def test_compra_antigua_se_ignora_y_venta_antigua_se_copia(tmp_path, monkeypatch):
    b = crear(tmp_path, monkeypatch)
    recibir(b, monkeypatch, op("compra", hace=60), "c0")
    assert b.estado["posiciones"] == {}
    recibir(b, monkeypatch, op("compra"), "c1")
    assert b.estado["posiciones"][MINT]["coste"] == 100          # 1000 × 1000/10000 = 100 (tope por token)
    recibir(b, monkeypatch, op("venta", antes=1000, hace=600), "v1")   # 10 min tarde: se vende igual
    assert b.estado["posiciones"] == {}


def test_venta_fallida_se_reintenta(tmp_path, monkeypatch):
    b = crear(tmp_path, monkeypatch)
    recibir(b, monkeypatch, op("compra"), "c1")
    b.jup.falla = True
    recibir(b, monkeypatch, op("venta", tokens=500, antes=1000), "v1")      # vende la mitad: falla
    p = b.estado["ventas_pendientes"][MINT]
    assert p["fraccion"] == 0.5 and p["intentos"] == 1 and MINT in b.estado["posiciones"]
    recibir(b, monkeypatch, op("venta", tokens=250, antes=500), "v2")       # otra mitad de lo que queda: falla
    p = b.estado["ventas_pendientes"][MINT]
    assert abs(p["fraccion"] - 0.75) < 1e-9 and p["intentos"] == 2
    assert json.load(open(tmp_path / "estado.json"))["ventas_pendientes"][MINT]["intentos"] == 2
    b.jup.falla = False
    b.estado["ventas_pendientes"][MINT]["proximo"] = 0

    async def un_reintento():
        t = asyncio.create_task(b.reintentar_ventas())
        await asyncio.sleep(5.3)
        t.cancel()
    asyncio.run(un_reintento())
    assert b.estado["ventas_pendientes"] == {}
    assert abs(b.estado["posiciones"][MINT]["tokens"] - 25) < 1e-6           # queda el 25 % de 100 tokens


def test_saldo_en_real(tmp_path, monkeypatch):
    b = crear(tmp_path, monkeypatch, modo="real")
    async def ejecutar(q):
        return True, "firma"
    b._ejecutar = ejecutar
    b.estado["posiciones"][MINT] = {"tokens": 40.0, "coste": 40.0, "decimales": 6}
    for saldo, esperado in ((None, 90.0), (40.0, 140.0), (187.0, 187.0)):   # sin dato / sin reflejar / correcto
        async def saldo_token(_, __, s=saldo):
            return s
        b.sol.saldo_token = saldo_token
        b.estado["posiciones"][MINT] = {"tokens": 40.0 if saldo != 40.0 else 90.0, "coste": 40.0, "decimales": 6}
        antes = b.estado["posiciones"][MINT]["tokens"]
        asyncio.run(b.copiar_compra(CART, op("compra", usd=500.0, tokens=500.0), "f", 1))
        assert abs(b.estado["posiciones"][MINT]["tokens"] - (antes + 50 if saldo != 187.0 else 187.0)) < 1e-6


def test_ordenes_con_clave(tmp_path, monkeypatch):
    b = crear(tmp_path, monkeypatch, env={"NTFY_CLAVE": "Secreta1"})
    assert b._autorizada("secreta1 vender todo") == "vender todo"
    assert b._autorizada("vender todo") is None and b._autorizada("otra parar") is None
    assert crear(tmp_path, monkeypatch)._autorizada("parar") == "parar"


def test_real_sin_clave_no_acepta_ordenes(tmp_path, monkeypatch):
    class K:
        @staticmethod
        def from_base58_string(_):
            class P:
                def pubkey(self):
                    return "yo"
            return P()
    import sys, types
    monkeypatch.setitem(sys.modules, "solders", types.ModuleType("solders"))
    m = types.ModuleType("solders.keypair"); m.Keypair = K
    monkeypatch.setitem(sys.modules, "solders.keypair", m)
    for env, activas in (({}, False), ({"NTFY_CLAVE": "x"}, True), ({"NTFY_TOKEN": "tk_x"}, True)):
        for k in ("NTFY_TOPIC", "NTFY_CLAVE", "NTFY_TOKEN", "NTFY_ORDENES"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("BOT_CLAVE_PRIVADA", "x")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        assert B.Bot(dict(CFG, datos=str(tmp_path), modo="real"), None).ordenes_activas is activas
