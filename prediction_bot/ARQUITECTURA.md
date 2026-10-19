# Bot de ineficiencias lógicas — Polymarket × Kalshi

Documento de diseño + análisis crítico. El código de la Fase 1 está en
[`scanner.py`](scanner.py) y se probó contra las APIs públicas reales el 2026-10-07.

---

## 0. Veredicto de viabilidad (léelo antes que nada)

| Estrategia | Viabilidad | Por qué |
|---|---|---|
| **Sum ≠ 100% intra-venue** | Media-baja como fuente de PnL; **alta como primer proyecto** | Los eventos líquidos ya los barren market makers. Lo que queda está en eventos poco líquidos (poca profundidad) o es un falso positivo (no exhaustivos, fees, libros vacíos). Es perfecto para construir la tubería de datos y el modo sombra. |
| **Cross-venue PM vs Kalshi** | Media, con matices graves | El edge existe, pero: (1) **riesgo de reglas**: misma pregunta ≠ mismo contrato (fuente, hora de corte, qué pasa si se cancela); (2) **riesgo de pata**: no hay atomicidad entre venues; (3) **capital inmovilizado** hasta la resolución; (4) **elegibilidad**: necesitas poder operar legalmente en *ambos* venues desde tu jurisdicción. Ese punto (4) puede matar el proyecto entero; resuélvelo primero. |
| **News-to-trade con LLM** | Baja si compites en velocidad, media si compites en interpretación | Contra bots que leen el mismo titular, unos cientos de ms de LLM pierden. El edge real está en (a) mercados de nicho donde nadie mira, y (b) **interpretar las reglas de resolución** frente a la noticia, algo que los bots simples no hacen. Nota: Claude 3.5 Haiku está obsoleto; usa `claude-haiku-4-5-20251001`. |

**Lo que de verdad mide la rentabilidad no es el ROI de la operación sino el ROI anualizado.**
Un 2 % que se resuelve en 18 meses rinde ~1,3 %/año, menos que una letra del Tesoro.
Filtra siempre por `edge / días_hasta_resolución`. Ten en cuenta también los rendimientos
que pagan los propios venues sobre posiciones (Kalshi paga interés sobre saldo y posiciones
elegibles; algunos mercados de Polymarket tienen `holdingRewardsEnabled`): cambian el cálculo.

Resultado de la primera pasada real del escáner (100 eventos PM + 25 Kalshi):
**0 arbitrajes verdaderos.** Detectó dos cestas YES en Kalshi con "ROI +514 %" y "+20 %":
ambos eran eventos `mutually_exclusive` pero **no exhaustivos** ("¿cuál será el estado 51?" puede
no tener ganador). Es exactamente el tipo de falso positivo que destruye cuentas, y por eso
ahora se excluyen por defecto.

---

## 1. Arquitectura técnica

### 1.1 Estructura del repositorio

```
prediction_bot/
├── pyproject.toml
├── .env.example                 # nombres de variables, NUNCA valores
├── config/
│   ├── settings.py              # pydantic-settings: carga y valida env + YAML
│   ├── risk.yaml                # límites (versionado, revisable en PR)
│   └── pairs.yaml               # mapeo MANUAL PM↔Kalshi con notas de reglas
├── core/
│   ├── models.py                # Level, OrderBook, Outcome, MultiEvent, Opportunity (Decimal)
│   ├── fees.py                  # fórmulas por venue/categoría, testeadas
│   └── clock.py                 # tiempo inyectable (backtests y tests deterministas)
├── data_pipeline/
│   ├── polymarket/
│   │   ├── rest.py              # Gamma (metadatos) + CLOB /books
│   │   └── ws.py                # canal market; libros locales
│   ├── kalshi/
│   │   ├── rest.py
│   │   ├── ws.py                # requiere auth; orderbook_delta con seq
│   │   └── auth.py              # firma RSA-PSS
│   ├── news/
│   │   ├── sources.py           # RSS / APIs / X — normalizados a NewsItem
│   │   └── classifier.py        # LLM → {market_id, direction, confidence, rationale}
│   └── book_store.py            # estado en memoria, frescura, resync
├── scanners/
│   ├── base.py                  # interfaz Scanner.evaluate(state) -> [Opportunity]
│   ├── basket.py                # Sum≠100% (LONG_YES exhaustivo / LONG_NO excluyente)
│   ├── cross_venue.py
│   └── news_signal.py
├── risk_manager/
│   ├── limits.py                # tamaño, exposición por evento/venue, pérdida diaria
│   ├── pretrade.py              # checks síncronos antes de cada orden
│   └── kill_switch.py           # archivo/flag/señal → cancelar todo y parar
├── executor/
│   ├── base.py                  # Executor ABC: place, cancel, positions
│   ├── paper.py                 # simula fills contra el libro + latencia
│   ├── polymarket_live.py       # py-clob-client; neg_risk, tick_size, firma
│   ├── kalshi_live.py
│   └── leg_manager.py           # orquesta patas, deshace pata huérfana
├── database/
│   ├── schema.sql               # snapshots, señales, órdenes, fills, PnL
│   └── repo.py                  # SQLite (fase 1-2) → Postgres/Timescale (fase 4)
├── ops/
│   ├── main.py                  # arranque: supervisa tareas asyncio
│   ├── metrics.py               # Prometheus / logs JSON
│   └── alerts.py                # Telegram/Slack
└── tests/
    ├── fixtures/                # respuestas reales grabadas de las APIs
    └── test_*.py
```

Principios:
- **Un solo modelo de datos** (`core/models.py`) al que se normaliza todo. Los scanners nunca ven JSON crudo de un venue.
- **`Decimal` para precios y tamaños.** `0.1 + 0.2 != 0.3` en float; en un umbral de arbitraje eso es un bug.
- **El executor es intercambiable** (`paper` / `live`) detrás de la misma interfaz: el modo sombra ejecuta exactamente el mismo código que producción salvo la última llamada.
- **La configuración de riesgo vive en Git** y se revisa como código.

### 1.2 Concurrencia y WebSockets

Un único event loop `asyncio`, con tareas independientes y colas entre ellas:

```
[PM ws ×N] ─┐                        ┌─> [scanner basket]   ─┐
[Kalshi ws] ─┼─> BookStore (memoria) ─┼─> [scanner xvenue]   ─┼─> Queue[Opportunity] ─> RiskManager ─> Executor
[REST resync]┘                        └─> [scanner news]     ─┘                                   └─> DB (cola async)
[news feeds] ──> classifier (LLM) ──────────┘
```

Reglas para no bloquear el loop:
1. **Nada síncrono en el loop.** `py-clob-client` es síncrono (usa `requests`): envuélvelo con `await asyncio.to_thread(client.post_order, ...)`. Lo mismo para la firma con KMS.
2. **El handler del WS solo actualiza estado.** El cálculo de oportunidades se dispara aparte (coalescido por evento cada X ms), no dentro de `async for msg in ws`.
3. **Escrituras a DB por cola**, en lotes; nunca un `INSERT` por mensaje dentro del handler.
4. **Supervisión**: cada tarea en un wrapper que la reinicia con backoff y alerta; si una tarea muere en silencio, el libro queda congelado y sigues "viendo" oportunidades que ya no existen.
5. **Reparte suscripciones** en varias conexiones (~500 tokens c/u en PM) para aislar fallos.
6. **Resync periódico por REST** (cada 1–5 min) y comparación contra el libro local. El WS de Polymarket no tiene números de secuencia: si pierdes un mensaje, tu libro está mal sin que nada lo indique.
7. Para Kalshi, `orderbook_delta` trae `seq`: si detectas un salto, descarta el libro y vuelve a suscribir para obtener snapshot.

`scanner.py` implementa 1–5 para Polymarket (`PolymarketBookStream`).

---

## 2. Autenticación y riesgo

### 2.1 Credenciales

**Polymarket**
- **L1** = clave privada de la wallet EOA. Sirve para derivar las credenciales L2 y **para firmar cada orden** (EIP-712). Es decir, la clave tiene que estar *disponible para firmar* en tiempo de ejecución; no basta con usarla una vez.
- **L2** = `api_key / secret / passphrase` (HMAC). Autentica las llamadas REST (enviar/cancelar órdenes, ver posiciones). Si se filtran, alguien puede cancelar tus órdenes o ver tu actividad, pero no puede firmar órdenes nuevas sin L1.
- Configura bien `signature_type` (0 = EOA, 1 = proxy de email/Magic, 2 = Gnosis Safe) y `funder` (la dirección que realmente tiene los fondos). Equivocarse aquí da errores de firma o de "saldo insuficiente" que parecen otra cosa.

**Kalshi**
- API key ID + **clave privada RSA**. Cada petición lleva `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP` (ms) y `KALSHI-ACCESS-SIGNATURE` = RSA-PSS-SHA256 de `timestamp + MÉTODO + path`.

**Niveles de protección (de mínimo a recomendado):**

1. **`.env` solo en desarrollo**, fuera de Git (`.gitignore` + `git-secrets`/`gitleaks` en pre-commit), permisos `600`, y **una wallet dedicada al bot** con el capital justo. Nunca tu wallet principal.
2. **Gestor de secretos en el VPS** (AWS Secrets Manager, GCP Secret Manager, Vault, Doppler, `systemd-creds`): el proceso lee el secreto al arrancar; no queda en disco ni en el historial del shell.
3. **KMS con firma remota** (la opción buena para L1): AWS KMS soporta claves `ECC_SECG_P256K1`, es decir, secp256k1, la curva de Ethereum. La clave **nunca sale del HSM**; el bot pide firmas. Hay que convertir la firma DER a `(r, s, v)` y normalizar `s` (low-s); librerías como `web3-kms-signer` o un `eth_account` custom lo resuelven. Coste: ~10–50 ms por firma, irrelevante para esta estrategia.
4. Para Kalshi, la clave RSA también puede vivir en KMS (`RSA_2048`, `RSASSA_PSS_SHA_256`).

Además: rotar L2 periódicamente, IP fija del VPS en allowlist donde se pueda, logs que **nunca** impriman headers ni bodies de auth (un `log.debug(request)` es la filtración más común).

### 2.2 Mecanismos de protección

**Slippage**
- Nunca órdenes "a mercado". Siempre **límite** con precio máximo = precio objetivo de la oportunidad + tolerancia (p. ej. 1 tick). Si no llena a ese precio, la oportunidad no existía.
- Tipos: Polymarket `FOK` / `FAK` (taker) o `GTC`/`GTD` (maker); Kalshi `time_in_force` `fill_or_kill` / `immediate_or_cancel`. Para arbitraje de patas, **FOK por pata**.
- Recalcula el edge con el libro de *ahora* justo antes de enviar (no con el de cuando se detectó la señal).

**Position sizing**
- Tamaño = `min(profundidad disponible al precio límite en la pata más fina, límite por operación, límite por evento − exposición actual, capital libre × f)`.
- Para arbitraje "seguro" no apliques Kelly; el riesgo dominante no es la varianza del resultado sino **reglas, pata huérfana y contraparte**. Usa límites duros: p. ej. ≤ 2 % del capital por operación, ≤ 5 % por evento, ≤ 50 % por venue.
- **Kill-switch** automático: pérdida diaria > X, N rechazos seguidos, libro sin actualizar > T segundos, divergencia entre posiciones locales y las del venue → cancelar todo y parar.

**Gestión de patas (cross-venue y cestas)**
- Ejecuta primero la pata **menos líquida** (la más difícil de llenar). Si falla, no has arriesgado nada.
- Si la segunda pata falla, el `leg_manager` decide: reintentar a peor precio dentro de un límite, o deshacer la primera. Registrar siempre el coste de las patas huérfanas: es tu coste real de ejecución.
- En cestas de N patas el riesgo de pata crece con N. Limita N o exige más edge por pata.

**Paper trading / Shadow Mode** (tres niveles, en este orden)
1. **Señal**: el scanner registra la oportunidad con el libro completo en ese instante.
2. **Sombra**: `PaperExecutor` simula la ejecución contra el libro *real* tras una latencia realista (p. ej. 300–800 ms), recorre niveles, aplica fees y rechaza si el precio se movió. Registra lo que *habría* pasado.
3. **Live mínimo**: mismo código, tamaño mínimo, para medir la diferencia entre el fill simulado y el real (*implementation shortfall*). Si la sombra dice +2 % y el live da −0,5 %, el simulador miente y hay que corregirlo antes de subir tamaño.

Criterio para pasar a dinero real: ≥ 4 semanas de sombra, ≥ 50 señales, PnL simulado positivo **después** de fees y latencia, y cero incidentes de libro corrupto.

---

## 3. Hoja de ruta

### Fase 1 — Scanner read-only (1–2 semanas) ✅ PoC hecho
- `scanner.py`: Gamma + CLOB `/books` + Kalshi REST, normalización, cestas con profundidad y fees, stream WS de Polymarket.
- Siguiente: persistir cada pasada en SQLite (snapshots + oportunidades), grabar fixtures para tests, añadir filtro de ROI anualizado.
- **Criterio de salida**: una semana de datos sin huecos; lista de "oportunidades" revisada a mano y clasificada (real / falso positivo y por qué).

### Fase 2 — Shadow mode + mapeo cross-venue (2–4 semanas)
- `PaperExecutor`, `risk_manager` completo, kill-switch, alertas.
- `pairs.yaml` curado a mano: para cada par, texto de reglas de ambos venues, fecha y hora de corte, fuente de resolución y casos límite. El LLM puede **proponer** pares candidatos; un humano los aprueba.
- Prototipo de `news/classifier.py` **solo registrando** predicciones con timestamp, para medir después si llegaban antes que el movimiento del precio.
- **Criterio de salida**: los de la sección 2.2.

### Fase 3 — Live con capital mínimo (2–4 semanas)
- Wallet dedicada, approvals (incluido el exchange de neg-risk), KMS para L1, credenciales L2 en el gestor de secretos.
- Solo estrategias que pasaron la sombra, tamaño mínimo, reconciliación de posiciones con el venue cada minuto.
- **Criterio de salida**: implementation shortfall medido y estable; ningún desajuste de posiciones sin explicar.

### Fase 4 — VPS 24/7 (continuo)
- VPS cerca de la infraestructura de los venues (US-East es razonable para ambos), con IP estática.
- `systemd` o Docker con `restart=always`, healthcheck que comprueba **frescura de libros**, no solo que el proceso esté vivo.
- Postgres/Timescale, Prometheus + Grafana, alertas a Telegram, backups diarios de la DB.
- Despliegue por CI con tests sobre fixtures; el kill-switch se puede activar desde el móvil.
- Runbook escrito: qué hacer si un venue cae, si un mercado se resuelve de forma disputada, si la wallet se queda sin MATIC/POL para gas (approvals, redenciones).

---

## 4. Silent bugs y trampas (verificadas o muy frecuentes)

**Datos de mercado**
1. **Libros ordenados al revés.** Tanto `/book` de Polymarket como el orderbook de Kalshi devuelven niveles en orden **ascendente** de precio: el mejor bid es el *último*. `bids[0]` te da el peor bid. *(Verificado.)*
2. **Kalshi solo publica bids.** No hay asks: el ask de YES es `1 − mejor bid de NO`, con el tamaño de ese bid. *(Verificado.)*
3. **Kalshi cambió el formato** a `orderbook_fp` con `yes_dollars`/`no_dollars` en strings decimales; el formato antiguo `orderbook.yes` iba en centavos enteros. Código antiguo o SDKs desactualizados leen listas vacías y "no ven" liquidez. *(Verificado; el scanner soporta ambos.)*
4. **`clobTokenIds`, `outcomes` y `outcomePrices` de Gamma son strings con JSON dentro**, no listas. `m["clobTokenIds"][0]` devuelve `'['`. *(Verificado.)*
5. **Evento `active=true` con mercados cerrados dentro.** Hay que filtrar por mercado (`closed`, `enableOrderBook`, `acceptingOrders`). *(Verificado: el primer evento devuelto tenía `closed=True` en sus mercados.)*
6. **`outcomePrices` / `lastTradePrice` no son precios ejecutables.** Un mercado puede mostrar 0,40 con el libro vacío en ese lado. Usa siempre el libro y su profundidad.
7. **El `timestamp` del libro de Polymarket es la hora del último cambio**, no la del snapshot. Si mides la frescura con él, descartas libros válidos pero quietos. *(Verificado: me pasó en la primera versión del scanner.)*
8. **`price_change` trae el tamaño absoluto nuevo del nivel**, no un delta. Sumarlo corrompe el libro poco a poco.
9. **Sin secuencia en el WS de Polymarket**: un mensaje perdido deja el libro mal para siempre. Resync REST periódico obligatorio.
10. **Exhaustividad**: `mutually_exclusive` (Kalshi) no implica que alguna opción gane. En Polymarket, `negRiskAugmented` indica que pueden aparecer opciones nuevas o placeholders "Other". Comprar todos los YES en esos eventos es una apuesta. *(Verificado: fueron los dos falsos positivos.)*
11. **Combos multivariantes de Kalshi** (`KXMVE…`) inundan los listados con miles de mercados sin liquidez. Fíltralos.

**Ejecución**
12. **Mercados neg-risk usan otro contrato exchange**: la orden debe firmarse con `neg_risk=True` y necesitas approval de ese contrato. Si no, rechazo con un error de firma que no menciona neg-risk.
13. **`tick_size` cambia** (0,01 → 0,001 cerca de los extremos; evento `tick_size_change` en el WS). Una orden con precio fuera de tick se rechaza; redondear mal puede pasar tu límite.
14. **`orderMinSize`** (p. ej. 5 shares): cestas con patas pequeñas no se pueden ejecutar aunque el edge exista.
15. **Fees por categoría**: Polymarket ya cobra taker fees en varias categorías (`feesEnabled`, `feeSchedule` con `rate`/`exponent` por mercado). La fórmula del scanner es una aproximación: **verifícala contra la documentación vigente** antes de operar. Kalshi redondea la fee **hacia arriba al centavo por orden**, lo que penaliza muchas órdenes pequeñas.
16. **Firma de Kalshi**: el path firmado va **sin query string**. Firmar `/trade-api/v2/portfolio/orders?limit=5` da 401 intermitentes difíciles de rastrear. Y el timestamp en milisegundos, con el reloj sincronizado (NTP).
17. **Rate limits**: los 429 en mitad de una ejecución de patas son peores que no operar. Presupuesto de peticiones separado para lectura y para órdenes.
18. **`py-clob-client` es síncrono**: llamarlo desde el loop bloquea todos los WebSockets mientras dura la petición.

**Resolución y contraparte**
19. **Misma pregunta, distinto contrato.** Diferencias típicas: zona horaria del corte, "a las 23:59 ET" vs "al cierre", fuente (AP vs oficial), qué pasa si se pospone o cancela, redondeos en mercados numéricos. Una sola diferencia convierte un arbitraje en una apuesta doble.
20. **Riesgo de oráculo**: Polymarket resuelve con UMA (disputable, con resoluciones polémicas documentadas); Kalshi con su propio equipo según reglas. Pueden resolver distinto el mismo hecho.
21. **Capital y colateral**: en Polymarket el capital queda en la wallet en Polygon (colateral en stablecoin; verifica cuál usa el CLOB actual). Mover fondos entre venues lleva horas o días; rebalancear no es instantáneo, así que un venue puede quedarse sin saldo justo cuando aparece la oportunidad.

---

## 5. Cómo ejecutar el PoC

```bash
cd prediction_bot
pip install -r requirements.txt
python scanner.py --once                       # una pasada (~1 min por rate limits de Kalshi)
python scanner.py --loop 60                    # cada 60 s
python scanner.py --stream                     # libros Polymarket en vivo
python scanner.py --once --allow-non-exhaustive   # ver también cestas YES no exhaustivas
python scanner.py --once --pairs pairs.json    # cross-venue (ver pairs.example.json)
```
