"""Copybot SIMULADO de perpetuos de Hyperliquid (no envía órdenes; no necesita claves).

Uso: python bot.py config.json <carpeta_datos>
- Escucha los fills de cada trader por WebSocket (userFills) y, tras cada fill, ajusta nuestra posición en esa
  moneda a: su posición x (capital de su porción / capital del trader). Cada trader tiene una porción del capital
  (peso) que gana o pierde por separado. Apalancamiento máximo por porción: apalancamiento_max x su capital.
- Las posiciones que el trader ya tenía al arrancar el bot no se copian (se espera a que las cierre).
- Precio simulado: el del fill del trader con deslizamiento + comisión de taker.
- Cada 5 min comprueba que el trader sigue teniendo lo que copiamos (por si se perdió un fill); cada minuto
  valora con precios medios. Avisos por ntfy si existe NTFY_TOPIC.
"""
import asyncio, csv, json, os, sys, time
import aiohttp, websockets

INFO, WS = "https://api.hyperliquid.xyz/info", "wss://api.hyperliquid.xyz/ws"
CFG = json.load(open(sys.argv[1])); DATOS = sys.argv[2]; os.makedirs(DATOS, exist_ok=True)
EST = os.path.join(DATOS, "estado.json"); OPS = os.path.join(DATOS, "operaciones.csv"); RES = os.path.join(DATOS, "resumen.csv")
NTFY = os.environ.get("NTFY_TOPIC", "")
T = {k.lower(): v for k, v in CFG["traders"].items()}

def log(m): print(time.strftime("%Y-%m-%d %H:%M:%S ", time.gmtime()) + m, flush=True)
def dex_de(c): return c.split(":")[0] if ":" in c else ""

class Bot:
    def __init__(self, s):
        self.s = s; self.precios = {}; self.capital_suyo = {}; self.vistos = set()
        if os.path.exists(EST):
            e = json.load(open(EST)); self.porc = e["porciones"]; self.ignorar = e["ignorar"]; self.dia = e.get("dia")
        else:
            self.porc = {t: {"caja": CFG["capital_usd"] * v["peso"], "pos": {}} for t, v in T.items()}
            self.ignorar = None; self.dia = None
        for t, v in T.items():
            self.porc.setdefault(t, {"caja": CFG["capital_usd"] * v["peso"], "pos": {}})

    async def info(self, body):
        for i in range(4):
            try:
                async with self.s.post(INFO, json=body, timeout=20) as r:
                    if r.status == 200: return await r.json()
            except Exception: pass
            await asyncio.sleep(1 + 2 * i)

    async def aviso(self, titulo, texto):
        if not NTFY: return
        try: await self.s.post("https://ntfy.sh/", json={"topic": NTFY, "title": titulo, "message": texto, "tags": ["chart_with_upwards_trend"]}, timeout=10)
        except Exception: pass

    def guardar(self):
        json.dump({"porciones": self.porc, "ignorar": self.ignorar, "dia": self.dia}, open(EST + ".tmp", "w"), indent=1)
        os.replace(EST + ".tmp", EST)

    def capital(self, t, px=None):
        p = self.porc[t]; v = p["caja"]
        for c, (q, ent) in p["pos"].items(): v += q * ((px or self.precios).get(c, ent) - ent)
        return v

    async def posiciones_trader(self, t, dexes):
        out = {}
        for d in dexes:
            r = await self.info({"type": "clearinghouseState", "user": t, **({"dex": d} if d else {})}) or {}
            for a in r.get("assetPositions", []):
                q = float(a["position"]["szi"])
                if q: out[a["position"]["coin"]] = q
        return out

    async def refrescar_capitales(self):
        for t in T:
            p = await self.info({"type": "portfolio", "user": t})
            try: self.capital_suyo[t] = max(float(dict(p)["day"]["accountValueHistory"][-1][1]), 1.0)
            except Exception: pass

    async def refrescar_precios(self):
        dexes = {""} | {dex_de(c) for p in self.porc.values() for c in p["pos"]}
        for d in dexes:
            r = await self.info({"type": "allMids", **({"dex": d} if d else {})}) or {}
            self.precios.update({k: float(v) for k, v in r.items()})

    def operar(self, t, c, objetivo, px, motivo, retraso=None):
        p = self.porc[t]; q, ent = p["pos"].get(c, [0.0, 0.0])
        if abs(objetivo - q) * px < CFG["min_operacion_usd"] and objetivo != 0: return
        if objetivo == 0 and q == 0: return
        lado = 1 if objetivo > q else -1
        pe = px * (1 + lado * CFG["desliz"]["hip3" if ":" in c else "normal"])
        nocional = abs(objetivo - q) * pe; p["caja"] -= nocional * CFG["comision"]; realizado = 0.0
        if q and (objetivo * q <= 0 or abs(objetivo) < abs(q)):
            cerrar = q if objetivo * q <= 0 else q - objetivo
            realizado = cerrar * (pe - ent); p["caja"] += realizado
        if objetivo and q * objetivo <= 0: ent = pe
        elif objetivo and abs(objetivo) > abs(q): ent = (ent * q + pe * (objetivo - q)) / objetivo
        if objetivo: p["pos"][c] = [objetivo, ent]
        else: p["pos"].pop(c, None)
        nuevo = not os.path.exists(OPS)
        with open(OPS, "a", newline="") as f:
            w = csv.writer(f)
            if nuevo: w.writerow(["ts", "trader", "moneda", "antes", "despues", "precio", "nocional_usd", "realizado_usd", "capital_porcion", "motivo", "retraso_s"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), T[t]["nombre"], c, round(q, 6), round(objetivo, 6), pe,
                        round(nocional, 2), round(realizado, 2), round(self.capital(t), 2), motivo, retraso])
        accion = "abre" if q == 0 else "cierra" if objetivo == 0 else "invierte" if q * objetivo < 0 else "ajusta"
        log(f"{T[t]['nombre']} {accion} {c} {q:+.4g} -> {objetivo:+.4g} @ {pe:.6g} ({nocional:,.0f} $) realizado {realizado:+.2f} $ [{motivo}]")
        self.guardar()
        if accion != "ajusta":
            asyncio.create_task(self.aviso(f"Perps {T[t]['nombre']} {accion} {c}", f"{'LARGO' if objetivo > 0 else 'CORTO' if objetivo < 0 else ''} "
                                           f"{nocional:,.0f} $ @ {pe:.6g} · realizado {realizado:+.2f} $ · porción {self.capital(t):,.0f} $"))

    def al_fill(self, t, f):
        c = f["coin"]
        if c.startswith("@") or "/" in c or f["tid"] in self.vistos: return
        self.vistos.add(f["tid"])
        suya = float(f["startPosition"]) + float(f["sz"]) * (1 if f["side"] == "B" else -1)
        ign = self.ignorar.setdefault(t, [])
        if c in ign:
            if abs(suya) < 1e-12: ign.remove(c); self.guardar()
            return
        px = float(f["px"]); cap = self.capital(t); k = cap / self.capital_suyo.get(t, 1e18)
        objetivo = suya * k
        # tope de apalancamiento de la porción
        otras = sum(abs(q) * self.precios.get(cc, e) for cc, (q, e) in self.porc[t]["pos"].items() if cc != c)
        libre = max(CFG["apalancamiento_max"] * cap - otras, 0)
        if abs(objetivo) * px > libre: objetivo = (libre / px) * (1 if objetivo > 0 else -1)
        self.operar(t, c, objetivo, px, "fill", round(time.time() - f["time"] / 1000, 1))

    async def escuchar(self):
        espera = 1
        while True:
            try:
                async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
                    for t in T:
                        await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "userFills", "user": t, "aggregateByTime": True}}))
                    log(f"escuchando {len(T)} traders"); espera = 1
                    async def ping():
                        while True: await asyncio.sleep(30); await ws.send(json.dumps({"method": "ping"}))
                    pt = asyncio.create_task(ping())
                    try:
                        async for msg in ws:
                            d = json.loads(msg)
                            if d.get("channel") != "userFills": continue
                            data = d["data"]; t = data.get("user", "").lower()
                            if t not in T: continue
                            for f in sorted(data.get("fills", []), key=lambda f: (f["time"], f["tid"])):
                                if data.get("isSnapshot"): self.vistos.add(f["tid"]); continue
                                self.al_fill(t, f)
                    finally: pt.cancel()
            except Exception as e:
                log(f"conexión perdida ({type(e).__name__}); reconecto en {espera} s")
                await asyncio.sleep(espera); espera = min(espera * 2, 30)

    async def revisar(self):
        """Cada 5 min: si el trader ya no tiene la posición que copiamos (fill perdido), la cerramos."""
        while True:
            await asyncio.sleep(300)
            for t, p in self.porc.items():
                if not p["pos"]: continue
                suyas = await self.posiciones_trader(t, {dex_de(c) for c in p["pos"]})
                for c, (q, _) in list(p["pos"].items()):
                    s = suyas.get(c, 0.0)
                    if s == 0 or s * q < 0:
                        self.operar(t, c, 0.0, self.precios.get(c, p["pos"][c][1]), "revisión: él ya no la tiene")

    async def periodico(self):
        n = 0
        while True:
            await self.refrescar_precios()
            if n % 30 == 0: await self.refrescar_capitales()
            if n % 10 == 0:
                fila = {T[t]["nombre"]: round(self.capital(t), 2) for t in T}
                total = round(sum(fila.values()), 2); nuevo = not os.path.exists(RES)
                with open(RES, "a", newline="") as f:
                    w = csv.writer(f)
                    if nuevo: w.writerow(["ts", "total"] + list(fila))
                    w.writerow([time.strftime("%Y-%m-%d %H:%M", time.gmtime()), total] + list(fila.values()))
                hoy = time.strftime("%Y-%m-%d", time.gmtime())
                if self.dia and self.dia != hoy:
                    mejor = sorted(fila.items(), key=lambda x: -x[1])
                    await self.aviso("Perps: resumen diario", f"Total {total:,.0f} $ ({total / CFG['capital_usd'] - 1:+.1%}) · "
                                     + " · ".join(f"{k} {v:,.0f}" for k, v in mejor))
                self.dia = hoy; self.guardar()
            n += 1; await asyncio.sleep(60)

    async def correr(self):
        await self.refrescar_capitales(); await self.refrescar_precios()
        if self.ignorar is None:
            dexes = [""] + [d["name"] for d in (await self.info({"type": "perpDexs"}) or []) if d]
            self.ignorar = {}
            for t in T: self.ignorar[t] = list((await self.posiciones_trader(t, dexes)).keys())
            log("posiciones previas (no se copian): " + ", ".join(f"{T[t]['nombre']}={len(v)}" for t, v in self.ignorar.items()))
            self.guardar()
        log(f"modo simulado · capital {CFG['capital_usd']} $ · {len(T)} traders")
        await asyncio.gather(self.escuchar(), self.revisar(), self.periodico())

async def main():
    async with aiohttp.ClientSession() as s: await Bot(s).correr()

if __name__ == "__main__": asyncio.run(main())
