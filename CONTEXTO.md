# Contexto del proyecto (para continuar en una sesión nueva)

Usuario: responde siempre en español; eficiente en tokens. Solo memecoins/copy trading en este
repositorio (nada de acciones ni del repo An-lisis-cuantitativo / Smallcaps-AI).

## Herramientas
- Clave de Helius en la variable de entorno `HELIUS_API_KEY` (va en la URL:
  `https://mainnet.helius-rpc.com/?api-key=$HELIUS_API_KEY`; Helius no acepta la clave en cabecera).
- Sin Helius: RPC público de Solana (lento, limita `getTokenLargestAccounts`), GeckoTerminal
  (trades solo de 24 h), Jupiter (`lite-api.jup.ag`), Hyperliquid (`api.hyperliquid.xyz/info`).

## Trader 1: bystevenr (FOMO) — estudiado
- Solana `AH75Bn6QHSt5K2Ad4p1otns3JTwpSJWZTwiwKWNhmnKx` (99% de su actividad, desde 9-ago-2026).
- Ethereum e Hyperliquid `0xd0b3f02a7ce7669acb6eaf251e719f62426be440` (perpetuos: HYPE, XYZ100…).
- Estudios en `radar-memecoins/estudios/copia/`: copiar con 1-30 s de retraso cuesta ~3% de peor
  precio; con 3 meses de datos, sin tope por token la copia pierde (-8%) y con tope del 10% del
  capital por token gana (+33%). Agosto fue muy malo para él (-$116K realizado).
- Bot `copybot/` en modo simulado en GitHub Actions (`copybot-simulado.yml`, datos en la rama
  `copybot-datos`, carpeta `v2/`): $5K, factor = capital/259K, tope $500 por token. Otra sesión
  (Fable 5.2) añadió `copybot/ESTUDIO_HISTORIAL.md` y amplió la simulación hasta el 8-dic.

## Traders 2 y 3: pendientes de identificar
- **GuavaGuy2001** (FOMO): ~118 trades, ~12 días por posición, empezó al menos en enero 2026.
  Abiertas: 牛来 4.4M (+2,782%), mihao (`4CxjZyMNoF1p6eXHXHv1TWpS2X47CuUmLwtGe18spump`) 11.7M,
  KITTY (`4N4DnNo3qpPks9aQCkcWkzoir8tnvT6diS4TnnZibonk`, pool `7dNW2mhCtqoZcDuyRbj5LMoeFsS9TpaCdSkk4qMstGPm`) 4.7M.
  Ventas de KITTY: 20-oct 4:41 a.m. 253.8K ($14,669); 18-sep 9:43 p.m. 239.3K; 18-sep 3:01 a.m. 830.4K.
  Método previsto: `getTokenLargestAccounts` de mihao/KITTY con Helius y buscar el dueño con
  esas cantidades.
- **fomopumpguy (@fmpumpguy)**: 1.1K trades, ~12 h por posición, 30 d -$216K pero 牛来 9.6M
  (+58,328%). Token 孙小圣: compras 28-ago 11:44 p.m. $991.70 (7.6M) y 29-ago 12:02 a.m.
  $991.71 (2.9M); ventas 29-ago 11:12 a.m. 1.6M ($1,936)… hasta 1-sep 6:09 a.m. 2.1M ($5,281).
- Horas de las capturas del usuario: UTC-4 hasta el 1-nov y UTC-5 después (comprobar).
- Siguiente: identificar carteras, extraer historial completo y repetir el análisis
  (mes a mes, copia con retraso y topes) como con bystevenr.

## Avances (11-nov, madrugada)
- Helius funciona (`HELIUS_API_KEY` cargada).
- **牛来 está en BNB Chain** (`0xbeea1d618e533a387d941f58a7d4c9b7bd377777`, ~$0.059): GuavaGuy2001 (4.4M)
  y fomopumpguy (9.6M) operan también en BSC con una cartera EVM. Buscar sus direcciones EVM entre los
  poseedores de 牛来 (necesita un explorador/API de BSC o eth_getLogs de Transfer en un RPC de BSC).
- **Las transacciones de FOMO en Solana las firma un "relayer" de FOMO** (`AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51`),
  no la cartera del usuario: por eso aparecía en todos los tokens. Se puede usar para listar operaciones de
  FOMO, pero la cartera del trader es la dueña de las cuentas de tokens, no el firmante.
- Candidato Solana de GuavaGuy2001: `C481ZKiw4TZGs4EjNkhm6TB7s17swzmqAmCcNm73vGnW` (4.74M KITTY y 10.34M mihao;
  2,077 firmas desde 4-dic-2025; tiene transacciones a las 08:41 del 20-oct y 01:46 del 19-sep), **sin confirmar**:
  a las 08:41 compró 9.23M de `D42TjMjz…` por $15,000, no vendió KITTY. Verificar con otra operación.
