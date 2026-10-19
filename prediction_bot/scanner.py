"""
scanner.py — Escáner READ-ONLY de ineficiencias lógicas en Polymarket y Kalshi.

Prueba de concepto de la Fase 1. No firma nada, no necesita claves y no puede
enviar órdenes: solo lee libros de órdenes públicos y reporta oportunidades.

Qué detecta
-----------
1. Cestas "Sum != 100%" dentro de un evento multi-opción:
   - LONG_YES: comprar 1 YES de cada opción. Paga exactamente 1 si el evento es
     EXHAUSTIVO (alguna opción gana seguro). Edge si sum(asks YES) + fees < 1.
   - LONG_NO: comprar 1 NO de cada opción. Si las opciones son MUTUAMENTE
     EXCLUYENTES paga al menos n-1. Edge si sum(asks NO) + fees < n-1.
     No requiere exhaustividad, por eso es la variante más robusta.
2. Cross-venue (Polymarket vs Kalshi) para pares mapeados A MANO en pairs.json:
   comprar YES en un venue + NO en el otro; paga 1 si ambas reglas resuelven igual.

Todo se evalúa contra profundidad real (VWAP recorriendo el libro), no contra
el mid ni el "outcomePrices" de Gamma, y con comisiones de taker incluidas.

Uso
---
    pip install aiohttp websockets
    python scanner.py --once                 # una pasada REST, imprime tabla
    python scanner.py --loop 30              # repite cada 30 s
    python scanner.py --stream               # libros Polymarket en vivo por WS
    python scanner.py --once --pairs pairs.json   # añade cross-venue
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Callable, Iterable

import aiohttp

log = logging.getLogger("scanner")

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
PM_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
KALSHI_URL = "https://api.elections.kalshi.com/trade-api/v2"

ONE = Decimal(1)
ZERO = Decimal(0)


# ─────────────────────────────── Modelo de datos ───────────────────────────────

@dataclass(frozen=True)
class Level:
    price: Decimal  # en dólares por contrato, 0..1
    size: Decimal   # contratos/shares


@dataclass
class OrderBook:
    """Libro normalizado: bids DESC (mejor primero), asks ASC (mejor primero)."""
    venue: str
    instrument: str          # token_id (Polymarket) o "TICKER:YES|NO" (Kalshi)
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)
    ts: float = 0.0          # epoch seg. del snapshot (del venue si lo da)

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    def age(self) -> float:
        return time.time() - self.ts

    def cost_to_buy(self, qty: Decimal) -> tuple[Decimal, list[tuple[Decimal, Decimal]]] | None:
        """Coste de comprar `qty` recorriendo asks. None si no hay profundidad."""
        remaining, cost, fills = qty, ZERO, []
        for lvl in self.asks:
            take = min(remaining, lvl.size)
            cost += take * lvl.price
            fills.append((lvl.price, take))
            remaining -= take
            if remaining <= 0:
                return cost, fills
        return None


def _sorted_book(venue, instrument, bids, asks, ts) -> OrderBook:
    # TRAMPA: Polymarket y Kalshi devuelven los niveles en orden ASCENDENTE de
    # precio, así que el mejor bid es el ÚLTIMO. Ordenar siempre explícitamente.
    return OrderBook(
        venue=venue,
        instrument=instrument,
        bids=sorted((l for l in bids if l.size > 0), key=lambda l: l.price, reverse=True),
        asks=sorted((l for l in asks if l.size > 0), key=lambda l: l.price),
        ts=ts,
    )


# ─────────────────────────────── Comisiones ───────────────────────────────

def polymarket_taker_fee(fills, fee_schedule: dict | None) -> Decimal:
    """Fee taker de Polymarket según el `feeSchedule` del mercado (Gamma).

    Modelo: fee = shares * rate * (p * (1 - p)) ** exponent, por nivel.
    VERIFICAR contra la documentación vigente antes de operar: Polymarket ha
    cambiado el esquema varias veces y varía por categoría (feeType).
    """
    if not fee_schedule:
        return ZERO
    rate = Decimal(str(fee_schedule.get("rate", 0)))
    exp = int(fee_schedule.get("exponent", 1))
    return sum((q * rate * (p * (ONE - p)) ** exp for p, q in fills), ZERO)


def kalshi_taker_fee(fills) -> Decimal:
    """Fee taker de Kalshi: ceil(0.07 * C * P * (1-P)) al centavo, por orden.

    Algunas series (p. ej. índices) usan otro coeficiente: consultar la tabla.
    """
    raw = sum((Decimal("0.07") * q * p * (ONE - p) for p, q in fills), ZERO)
    return (raw * 100).to_integral_value(rounding=ROUND_CEILING) / 100


# ─────────────────────────────── Clientes REST ───────────────────────────────

class RateLimiter:
    """Token bucket mínimo: como mucho `rate` peticiones por segundo."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


async def get_json(session: aiohttp.ClientSession, url: str, limiter: RateLimiter,
                   *, method="GET", retries=4, **kw):
    for attempt in range(retries):
        await limiter.wait()
        try:
            async with session.request(method, url, **kw) as r:
                if r.status == 429 or r.status >= 500:
                    raise aiohttp.ClientResponseError(r.request_info, (), status=r.status)
                r.raise_for_status()
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == retries - 1:
                raise
            delay = 2 ** attempt
            log.warning("%s %s falló (%s); reintento en %ss", method, url, e, delay)
            await asyncio.sleep(delay)


@dataclass
class Outcome:
    """Una opción de un evento multi-opción, con los libros YES y NO."""
    label: str
    yes: OrderBook | None = None
    no: OrderBook | None = None
    fee_fn: Callable = kalshi_taker_fee


@dataclass
class MultiEvent:
    venue: str
    event_id: str
    title: str
    outcomes: list[Outcome]
    exhaustive: bool            # ¿garantiza que exactamente una opción gana?
    notes: str = ""


class PolymarketReader:
    def __init__(self, session: aiohttp.ClientSession):
        self.s = session
        self.gamma_rl = RateLimiter(5)
        self.clob_rl = RateLimiter(10)

    async def neg_risk_events(self, limit=100) -> list[dict]:
        evs = await get_json(
            self.s, f"{GAMMA_URL}/events", self.gamma_rl,
            params={"active": "true", "closed": "false", "limit": str(limit),
                    "order": "volume24hr", "ascending": "false"},
        )
        return [e for e in evs if e.get("negRisk")]

    async def books(self, token_ids: list[str]) -> dict[str, OrderBook]:
        out: dict[str, OrderBook] = {}
        for i in range(0, len(token_ids), 50):  # batch POST /books
            chunk = token_ids[i:i + 50]
            data = await get_json(self.s, f"{CLOB_URL}/books", self.clob_rl, method="POST",
                                  json=[{"token_id": t} for t in chunk])
            for b in data:
                out[b["asset_id"]] = parse_pm_book(b)
        return out

    async def multi_events(self, limit=100) -> list[MultiEvent]:
        raw = await self.neg_risk_events(limit)
        legs: list[tuple[dict, dict, str, str]] = []
        for e in raw:
            for m in e.get("markets", []):
                # TRAMPA: un evento "active" puede contener mercados ya cerrados
                # o sin libro. Y clobTokenIds es un STRING con JSON dentro.
                if m.get("closed") or not m.get("enableOrderBook") or not m.get("clobTokenIds"):
                    continue
                yes_id, no_id = json.loads(m["clobTokenIds"])  # orden = outcomes ["Yes","No"]
                legs.append((e, m, yes_id, no_id))
        books = await self.books([t for *_, y, n in legs for t in (y, n)])

        events: dict[str, MultiEvent] = {}
        for e, m, yes_id, no_id in legs:
            ev = events.get(e["id"])
            if ev is None:
                # negRiskAugmented = el set de opciones puede crecer (placeholders
                # "Other"/nuevos candidatos) → NO tratar la cesta YES como exhaustiva.
                augmented = bool(e.get("negRiskAugmented"))
                ev = events[e["id"]] = MultiEvent(
                    "polymarket", e.get("slug", e["id"]), e.get("title", ""), [],
                    exhaustive=not augmented,
                    notes="augmented" if augmented else "",
                )
            fs = m.get("feeSchedule") if m.get("feesEnabled") else None
            ev.outcomes.append(Outcome(
                label=m.get("groupItemTitle") or m.get("question", ""),
                yes=books.get(yes_id), no=books.get(no_id),
                fee_fn=lambda fills, fs=fs: polymarket_taker_fee(fills, fs),
            ))
        return [ev for ev in events.values() if len(ev.outcomes) >= 2]


def parse_pm_book(b: dict) -> OrderBook:
    lv = lambda xs: [Level(Decimal(x["price"]), Decimal(x["size"])) for x in xs]
    # TRAMPA: `timestamp` es la hora del ÚLTIMO CAMBIO del libro, no la del
    # snapshot. Un libro quieto lleva un timestamp antiguo pero es válido; la
    # frescura se mide por la hora de recepción.
    return _sorted_book("polymarket", b["asset_id"], lv(b.get("bids", [])),
                        lv(b.get("asks", [])), time.time())


class KalshiReader:
    def __init__(self, session: aiohttp.ClientSession, rps: float = 8):
        self.s = session
        self.rl = RateLimiter(rps)  # tier básico ≈ 20 lecturas/s; dejamos margen

    async def events(self, max_events=60) -> list[dict]:
        out, cursor = [], None
        while len(out) < 1000:
            params = {"status": "open", "limit": "200", "with_nested_markets": "true"}
            if cursor:
                params["cursor"] = cursor
            d = await get_json(self.s, f"{KALSHI_URL}/events", self.rl, params=params)
            out += d.get("events", [])
            cursor = d.get("cursor")
            if not cursor:
                break
        me = [e for e in out
              if e.get("mutually_exclusive") and len(e.get("markets") or []) >= 2
              and not e["event_ticker"].startswith("KXMVE")]  # combos multivariantes
        me.sort(key=lambda e: -sum(float(m.get("volume_24h_fp") or 0) for m in e["markets"]))
        return me[:max_events]

    async def book(self, ticker: str, depth=20) -> tuple[OrderBook, OrderBook]:
        d = await get_json(self.s, f"{KALSHI_URL}/markets/{ticker}/orderbook",
                           self.rl, params={"depth": str(depth)})
        return parse_kalshi_book(ticker, d)

    async def multi_events(self, max_events=60) -> list[MultiEvent]:
        evs = await self.events(max_events)
        result = []
        for e in evs:
            markets = [m for m in e["markets"] if m.get("status") in ("active", "open")]
            books = await asyncio.gather(*(self.book(m["ticker"]) for m in markets),
                                         return_exceptions=True)
            outcomes = [
                Outcome(m.get("yes_sub_title") or m["ticker"], yes=b[0], no=b[1])
                for m, b in zip(markets, books) if not isinstance(b, BaseException)
            ]
            if len(outcomes) >= 2:
                # mutually_exclusive NO implica exhaustivo (puede no ganar nadie).
                result.append(MultiEvent("kalshi", e["event_ticker"], e.get("title", ""),
                                         outcomes, exhaustive=False))
        return result


def parse_kalshi_book(ticker: str, d: dict) -> tuple[OrderBook, OrderBook]:
    """Kalshi solo publica BIDS de YES y de NO. Un bid NO a p equivale a un ask
    YES a 1-p (y viceversa). El formato actual es `orderbook_fp` con strings en
    dólares; el antiguo `orderbook` usaba enteros en centavos."""
    ob = d.get("orderbook_fp")
    if ob is not None:
        yes = [Level(Decimal(p), Decimal(q)) for p, q in ob.get("yes_dollars") or []]
        no = [Level(Decimal(p), Decimal(q)) for p, q in ob.get("no_dollars") or []]
    else:  # formato legado en centavos
        ob = d.get("orderbook") or {}
        yes = [Level(Decimal(p) / 100, Decimal(q)) for p, q in ob.get("yes") or []]
        no = [Level(Decimal(p) / 100, Decimal(q)) for p, q in ob.get("no") or []]
    now = time.time()
    flip = lambda lv: [Level(ONE - l.price, l.size) for l in lv]
    yes_book = _sorted_book("kalshi", f"{ticker}:YES", yes, flip(no), now)
    no_book = _sorted_book("kalshi", f"{ticker}:NO", no, flip(yes), now)
    return yes_book, no_book


# ─────────────────────────────── Detección ───────────────────────────────

@dataclass
class Opportunity:
    kind: str
    venue: str
    event: str
    title: str
    qty: Decimal
    cost: Decimal
    fees: Decimal
    payout: Decimal
    caveat: str = ""

    @property
    def pnl(self) -> Decimal:
        return self.payout - self.cost - self.fees

    @property
    def roi(self) -> float:
        spend = self.cost + self.fees
        return float(self.pnl / spend) if spend else 0.0


def _basket(outcomes: Iterable[Outcome], side: str, qty: Decimal):
    """Coste + fees de comprar `qty` de `side` en todas las opciones, o None."""
    cost = fees = ZERO
    for o in outcomes:
        book = o.yes if side == "yes" else o.no
        if book is None:
            return None
        res = book.cost_to_buy(qty)
        if res is None:
            return None
        c, fills = res
        cost += c
        fees += o.fee_fn(fills)
    return cost, fees


def scan_multi_event(ev: MultiEvent, sizes=(10, 50, 100, 250), max_age=60.0,
                     min_roi=0.005, allow_non_exhaustive=False) -> list[Opportunity]:
    stale = [o.label for o in ev.outcomes
             for b in (o.yes, o.no) if b is not None and b.age() > max_age]
    if stale:
        log.debug("%s: libros viejos %s, se omite", ev.event_id, stale[:3])
        return []
    n = len(ev.outcomes)
    best: dict[str, Opportunity] = {}
    for q in map(Decimal, sizes):
        for side, payout, caveat in (
            ("yes", q, "" if ev.exhaustive else "¡evento NO exhaustivo: puede pagar 0!"),
            ("no", q * (n - 1), ""),
        ):
            if side == "yes" and not ev.exhaustive and not allow_non_exhaustive:
                continue  # cesta YES sin exhaustividad = apuesta, no arbitraje
            res = _basket(ev.outcomes, side, q)
            if res is None:
                continue
            cost, fees = res
            opp = Opportunity(f"LONG_{side.upper()}_BASKET", ev.venue, ev.event_id,
                              ev.title, q, cost, fees, payout, caveat or ev.notes)
            if opp.roi >= min_roi and (opp.kind not in best or opp.pnl > best[opp.kind].pnl):
                best[opp.kind] = opp
    return list(best.values())


def sum_of_mids(ev: MultiEvent) -> float | None:
    """Métrica informativa (la de '< 98% o > 102%'). NO es una señal operable."""
    mids = []
    for o in ev.outcomes:
        if not o.yes or o.yes.best_bid is None or o.yes.best_ask is None:
            return None
        mids.append((o.yes.best_bid + o.yes.best_ask) / 2)
    return float(sum(mids))


def scan_cross_venue(pm_yes: OrderBook, pm_no: OrderBook, pm_fee: Callable,
                     k_yes: OrderBook, k_no: OrderBook, label: str,
                     sizes=(10, 50, 100), min_roi=0.01) -> list[Opportunity]:
    """YES en un venue + NO en el otro = 1 seguro, SOLO si las reglas son idénticas."""
    out = []
    for q in map(Decimal, sizes):
        for name, a, fa, b, fb in (
            ("PM_YES+K_NO", pm_yes, pm_fee, k_no, kalshi_taker_fee),
            ("K_YES+PM_NO", k_yes, kalshi_taker_fee, pm_no, pm_fee),
        ):
            ra, rb = a.cost_to_buy(q), b.cost_to_buy(q)
            if not ra or not rb:
                continue
            opp = Opportunity(f"XVENUE_{name}", "pm+kalshi", label, label, q,
                              ra[0] + rb[0], fa(ra[1]) + fb(rb[1]), q,
                              "verificar reglas de resolución y fechas de cierre")
            if opp.roi >= min_roi:
                out.append(opp)
    return out


# ─────────────────────────────── Stream WebSocket ───────────────────────────────

class PolymarketBookStream:
    """Mantiene libros locales de Polymarket vía WS (canal público `market`).

    - `book`: snapshot completo → reemplaza el libro.
    - `price_change`: `size` es el NUEVO tamaño absoluto del nivel (0 = borrar),
      NO un delta. Sumarlo es un silent bug clásico.
    - Reconexión con backoff exponencial; tras reconectar llega un snapshot nuevo.
    """

    def __init__(self, token_ids: list[str], on_update: Callable[[str, OrderBook], None] | None = None):
        self.token_ids = token_ids
        self.on_update = on_update
        self.books: dict[str, OrderBook] = {}
        self._bids: dict[str, dict[Decimal, Decimal]] = {}
        self._asks: dict[str, dict[Decimal, Decimal]] = {}

    def _rebuild(self, asset: str, ts: float):
        b = _sorted_book("polymarket", asset,
                         [Level(p, s) for p, s in self._bids[asset].items()],
                         [Level(p, s) for p, s in self._asks[asset].items()], ts)
        self.books[asset] = b
        if self.on_update:
            self.on_update(asset, b)

    def _handle(self, msg: dict):
        et = msg.get("event_type")
        if et == "book" or ("bids" in msg and "asset_id" in msg):
            a = msg["asset_id"]
            self._bids[a] = {Decimal(x["price"]): Decimal(x["size"]) for x in msg.get("bids", [])}
            self._asks[a] = {Decimal(x["price"]): Decimal(x["size"]) for x in msg.get("asks", [])}
            self._rebuild(a, time.time())
        elif et == "price_change":
            touched = set()
            for ch in msg.get("price_changes", []):
                a = ch["asset_id"]
                if a not in self._bids:
                    continue  # sin snapshot previo: ignorar hasta recibir `book`
                side = self._bids[a] if ch["side"] == "BUY" else self._asks[a]
                p, s = Decimal(ch["price"]), Decimal(ch["size"])
                if s == 0:
                    side.pop(p, None)
                else:
                    side[p] = s
                touched.add(a)
            for a in touched:
                self._rebuild(a, time.time())

    async def run(self, stop: asyncio.Event | None = None):
        import websockets  # import diferido: solo hace falta en --stream

        stop = stop or asyncio.Event()
        backoff = 1
        while not stop.is_set():
            try:
                async with websockets.connect(PM_WS_URL, open_timeout=10,
                                              ping_interval=20, max_size=2 ** 24) as ws:
                    await ws.send(json.dumps({"assets_ids": self.token_ids, "type": "market"}))
                    log.info("WS conectado, %d tokens", len(self.token_ids))
                    backoff = 1
                    async for raw in ws:
                        if stop.is_set():
                            break
                        if raw in ("PONG", "pong"):
                            continue
                        data = json.loads(raw)
                        for msg in data if isinstance(data, list) else [data]:
                            self._handle(msg)
            except Exception as e:  # noqa: BLE001 — cualquier caída → reconectar
                log.warning("WS caído (%s); reconectando en %ss", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)


# ─────────────────────────────── Orquestación ───────────────────────────────

def print_report(opps: list[Opportunity], mids: list[tuple[str, str, int, float]]):
    print(f"\n=== {time.strftime('%H:%M:%S')} · {len(opps)} oportunidades ===")
    for o in sorted(opps, key=lambda o: -o.pnl):
        print(f"[{o.venue:>10}] {o.kind:<18} qty={o.qty:<5} coste={o.cost:.2f} "
              f"fees={o.fees:.2f} pago={o.payout:.2f} PnL={o.pnl:+.2f} ROI={o.roi:+.2%}  "
              f"{o.title[:50]} {('⚠ ' + o.caveat) if o.caveat else ''}")
    off = [m for m in mids if abs(m[3] - 1) > 0.02]
    if off:
        print(f"--- {len(off)} eventos con suma de mids fuera de [98%,102%] (informativo) ---")
        for venue, title, n, s in sorted(off, key=lambda m: -abs(m[3] - 1))[:15]:
            print(f"[{venue:>10}] n={n:<3} Σmid={s:6.1%}  {title[:70]}")


async def scan_once(args) -> list[Opportunity]:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "ro-scanner/0.1"}) as s:
        pm, ks = PolymarketReader(s), KalshiReader(s)
        pm_evs, k_evs = await asyncio.gather(pm.multi_events(args.pm_events),
                                             ks.multi_events(args.kalshi_events))
        opps, mids = [], []
        for ev in pm_evs + k_evs:
            opps += scan_multi_event(ev, allow_non_exhaustive=args.allow_non_exhaustive)
            if (m := sum_of_mids(ev)) is not None:
                mids.append((ev.venue, ev.title, len(ev.outcomes), m))
        if args.pairs:
            opps += await scan_pairs(s, pm, ks, Path(args.pairs))
        log.info("Escaneados %d eventos PM y %d Kalshi", len(pm_evs), len(k_evs))
        print_report(opps, mids)
        return opps


async def scan_pairs(s, pm: PolymarketReader, ks: KalshiReader, path: Path) -> list[Opportunity]:
    """pairs.json: [{"label": "...", "pm_yes": "<token>", "pm_no": "<token>",
                     "kalshi": "<TICKER>", "pm_fee": {"rate":0.05,"exponent":1}}]

    El mapeo es MANUAL a propósito: emparejar por similitud de texto es la forma
    más rápida de perder dinero (fechas, fuentes y redacciones de reglas difieren).
    """
    pairs = json.loads(path.read_text())
    books = await pm.books([t for p in pairs for t in (p["pm_yes"], p["pm_no"])])
    out = []
    for p in pairs:
        ky, kn = await ks.book(p["kalshi"])
        fee = lambda f, fs=p.get("pm_fee"): polymarket_taker_fee(f, fs)
        if p["pm_yes"] in books and p["pm_no"] in books:
            out += scan_cross_venue(books[p["pm_yes"]], books[p["pm_no"]], fee, ky, kn, p["label"])
    return out


async def stream_demo(args):
    """Suscribe los tokens de los eventos negRisk top y re-evalúa al vuelo."""
    async with aiohttp.ClientSession() as s:
        pm = PolymarketReader(s)
        evs = await pm.multi_events(args.pm_events)
    by_token: dict[str, MultiEvent] = {}
    tokens = []
    for ev in evs:
        for o in ev.outcomes:
            for b in (o.yes, o.no):
                if b:
                    by_token[b.instrument] = ev
                    tokens.append(b.instrument)

    def on_update(asset: str, book: OrderBook):
        ev = by_token[asset]
        for o in ev.outcomes:  # sustituir el libro actualizado dentro del evento
            if o.yes and o.yes.instrument == asset:
                o.yes = book
            elif o.no and o.no.instrument == asset:
                o.no = book
        # Con WS vivo un libro quieto sigue siendo válido: la frescura la vigila
        # la conexión (ping/reconexión), no la edad de cada libro.
        for opp in scan_multi_event(ev, max_age=float("inf")):
            print(f"{time.strftime('%H:%M:%S')} {opp.kind} {ev.title[:50]} "
                  f"qty={opp.qty} PnL={opp.pnl:+.2f} ROI={opp.roi:+.2%} {opp.caveat}")

    # El servidor acepta muchos assets por conexión, pero conviene repartir en
    # varias conexiones (~500 tokens c/u) para aislar fallos.
    streams = [PolymarketBookStream(tokens[i:i + 500], on_update)
               for i in range(0, len(tokens), 500)]
    await asyncio.gather(*(st.run() for st in streams))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="una pasada REST")
    ap.add_argument("--loop", type=int, metavar="SEG", help="repetir cada SEG segundos")
    ap.add_argument("--stream", action="store_true", help="WS Polymarket en vivo")
    ap.add_argument("--pairs", help="JSON con pares cross-venue mapeados a mano")
    ap.add_argument("--pm-events", type=int, default=100)
    ap.add_argument("--kalshi-events", type=int, default=40)
    ap.add_argument("--allow-non-exhaustive", action="store_true",
                    help="reportar también cestas YES en eventos no exhaustivos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.stream:
        asyncio.run(stream_demo(args))
    elif args.loop:
        async def loop():
            while True:
                try:
                    await scan_once(args)
                except Exception:  # noqa: BLE001
                    log.exception("pasada fallida")
                await asyncio.sleep(args.loop)
        asyncio.run(loop())
    else:
        asyncio.run(scan_once(args))


if __name__ == "__main__":
    main()
