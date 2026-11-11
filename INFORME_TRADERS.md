# Informe de traders de FOMO (11-nov-2026)

## 1. bystevenr — estudiado por completo
- Carteras: Solana `AH75Bn6QHSt5K2Ad4p1otns3JTwpSJWZTwiwKWNhmnKx`, EVM/Hyperliquid `0xd0b3f02a7ce7669acb6eaf251e719f62426be440`.
- PnL realizado por mes: ago −$116K, sep +$74K, oct +$66K, nov (hasta el 8) +$45K.
- Copiarlo: ~3% peor precio de entrada ya con 1 s de retraso; con 1 min de retraso se pierde la ventaja.
- Simulación de 3 meses con $5K: sin tope −8%; **con tope del 10% del capital por token +33%**.
- Simulación en vivo (v2, desde el 9-nov): 7 compras, $193 invertidos, valen ~$130, retraso mediano 1.3 s.

## 2. GuavaGuy2001 y fomopumpguy — carteras NO identificadas
- Sus tokens grandes están en **BNB Chain (BSC)**, no en Solana: 牛来 (`0xbeea…7777`, pools desde el 14-ago),
  孙小圣 y el KITTY que vendió Guava (el KITTY de Solana valía ~$3–4M y él vendió a $116–140M de capitalización).
- El candidato de Solana `C481ZKiw…` quedó **descartado**: sus operaciones de KITTY no coinciden.
- Para encontrar la cartera EVM hace falta historial de BSC (quién compró 牛来 entre el 14 y el 17-ago):
  - RPC público (publicnode): solo da registros recientes; lo antiguo pide token ("Archive requests require a personal token").
  - GeckoTerminal `top_holders` y la API de BscScan/Etherscan V2 piden clave.
- Sin la cartera no se puede sacar historial, resultados mensuales, simulación de copia ni Hyperliquid.

## 3. Consenso entre los 3
No se puede medir: bystevenr opera sobre todo en Solana y los otros dos en BSC (cadenas distintas, sin tokens en común
visibles). Un sistema de consenso tendría que vigilar varias cadenas.

## 4. Lo que sabemos por sus capturas
| | GuavaGuy2001 | fomopumpguy |
|---|---|---|
| Estilo | pocas operaciones (~118), ~12 días por posición | muchas (~1.1K), ~12 h por posición |
| Resultado | grandes ganadores sostenidos (KITTY) | −$216K en 30 días, pero 牛来 $999 → $579K |
| Copiable en tiempo real | sí (lento, el retraso importa poco) | difícil (rápido, muchas pérdidas pequeñas) |

## 5. Siguientes pasos (cualquiera de estos desbloquea el análisis)
1. Una clave gratis de **Etherscan API V2** (sirve para BSC) guardada como secreto del entorno, nunca en el chat.
2. O una operación suya de las **últimas 24 h** (hora exacta e importe): se cruza con las operaciones de GeckoTerminal.
3. O un token personal gratis de publicnode (allnodes) para consultas de archivo.

## Recomendación
- Seguir solo con bystevenr en el copybot (tope del 10% por token) hasta identificar las carteras de los otros dos.
- GuavaGuy2001 es el mejor candidato para añadir: mantiene posiciones días, así que copiarlo con segundos o minutos
  de retraso cuesta poco. fomopumpguy no es buen candidato para copia automática (pierde en conjunto y depende de un
  ganador extremo).
- Copiar en BSC exige ampliar el bot (otra cadena, otro agregador: p. ej. PancakeSwap/1inch).
