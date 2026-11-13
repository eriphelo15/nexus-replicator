# Búsqueda de carteras de Solana para copiar (13-nov-2026)

## Método
1. `tokens.py`: 26 memecoins de Solana nacidas desde el 15-jul con máximo desde el 1-ago y subida >= 100x (CoinGecko + Helius).
2. `tempranos.py`: compradores de sus primeras 6 h (Helius, orden ascendente): 8,161 carteras; 194 en >= 3 ganadores.
3. `analizar.py`: descarta bots (>200 tx/día) e inactivas; historial desde el 1-ago; PnL realizado por mes.
4. `simular.py`: copia con $5,000, $100 por compra, tope $500 por token, 3% de deslizamiento + 1% de comisión por lado.

## Resultado
- De 190 analizadas: 82 bots de alta frecuencia, 33 inactivas, 75 restantes. **Ninguna opera menos de 25 veces al día**:
  todas son bots de francotirador, no traders humanos.
- Solo 9 de 75 ganan al copiarlas, y no son fiables:
  - `FHgfsb…`, `3tgpbm…`, `6dtUFf…` y `9H8xpL…` (+ probablemente `3VjkDR…`, `F5CymC…`) son **el mismo operador**:
    compran ~$121 en los mismos ~1,600 tokens. Su copia da desde +10% hasta +625% según la cartera, o sea, ruido.
  - Ganaron sobre todo en septiembre y **casi dejaron de operar en noviembre** (13 operaciones).
  - Compran en los primeros segundos de vida del token: con 2 s de retraso el precio real sería mucho peor que el 3% supuesto.
  - `66B95E…` (+$19K, solo octubre) tiene el mismo patrón.
- **Conclusión: los compradores tempranos de los ganadores son bots y no sirven para copiar.**

## Siguiente método propuesto
Buscar carteras humanas como bystevenr: compradores en la fase de descubrimiento (capitalización $100K–$2M, no en
los primeros segundos), con <= 20 operaciones al día, que mantengan horas o días y ganen en varios meses.
