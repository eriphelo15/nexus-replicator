# Cuenta "Bilberry" (Polymarket, temperatura): ¿sigue funcionando? (20-oct-2026)

Revisión mínima de sus 10.000 últimas operaciones públicas (23-sep → 19-oct), con el resultado
real de cada mercado. Margen = ganancia / dinero invertido, **antes de comisiones (~1,6 %)**.

| Periodo | Operaciones | Ganancia | Invertido | Margen |
|---|---|---|---|---|
| 23–30 sep | 5.818 | +16.193 $ | 262.997 $ | 6,2 % |
| 1–10 oct | 2.888 | +1.405 $ | 190.065 $ | 0,7 % (negativo tras comisiones) |
| 11–19 oct | 904 | +895 $ | 16.469 $ | 5,4 % (muestra pequeña) |

- La ventaja de septiembre se hundió a principios de octubre y la cuenta redujo su volumen ~10 veces.
- Por tramos de precio el resultado cambia de signo de un periodo a otro: mucho ruido.
- Sus compras se reparten igual a todas horas; no se ve que se concentren tras la publicación
  de nuevas previsiones, así que no se puede confirmar el método del tuit con estos datos.

Conclusión: hubo un hueco real en septiembre, pero ya no es fiable. No merece la pena copiarlo.

## Prueba ligera: simular la regla del tuit (backtest.py)

15 ciudades, 735 mercados de temperatura máxima, 1-sep → 19-oct-2026. Apuestas de 25 $, con
deslizamiento y comisión. Decisión a las 23:00 locales de la víspera (no en minutos).

| Variante | Apuestas | Ganancia | Por apuesta |
|---|---|---|---|
| Regla del tuit (cambio ≥0,5 °C, precio 5–60 c) | 303 | +128 $ | +2 % |
| Sin exigir cambio | 626 | −401 $ | −3 % |
| Cambio ≥1 °C | 142 | +325 $ | +9 % |

Intervalo 90 % de la regla del tuit: −1.431 $ a +1.686 $ → **indistinguible de cero**.
La variante ≥1 °C es la mejor de 3 probadas; con 142 apuestas puede ser casualidad.

Conclusión: la versión "lenta" no gana. Si Bilberry gana, su ventaja estaría en la velocidad
(comprar a los pocos minutos de salir la nueva ejecución del modelo), que esta prueba no reproduce.

## 26-oct: cómo opera Bilberry (40 días, 19.438 operaciones)

- Compra **una vez por hora**: el 97 % de las compras entre hh:10 y hh:12 UTC (mediana hh:10:50).
- Gana sobre todo cerca del día: 0–12 h antes +9,3 %, durante el día +8,7 %, 24–36 h antes +1,5 %.
- Gana más comprando favoritos (60–90 c: +8–9 %) que tramos baratos (5–20 c: −0,5 %).
- Vende posiciones antes de resolverse cuando cambia la información (ventas +10 % frente a mantener).

## 26-oct: prueba "durante el día" solo con observaciones (nowcast.py)

- La máxima medida en el aeropuerto (METAR, archivo IEM) coincide con el tramo ganador en el **99 %**
  de 2.663 mercados → la fuente de datos es la correcta.
- Sin previsiones, el modelo (subida típica de días anteriores) **pierde**: −8,7 % por apuesta.
  El mercado ya sabe más que la climatología. Solo al final del día (18–24 h) gana, con muy pocas
  operaciones (13; +45 %).
- Conclusión: hace falta combinar observaciones con previsiones horarias recientes (siguiente paso).

## 27-oct: prueba combinada (METAR + 7 modelos con 1–2 días de retraso) — combinado.py

1. Primer resultado (+20 % por apuesta) era **falso**: al crearse un mercado Polymarket muestra precios
   de relleno (0,34 / 0,20 / 0,50) sin nadie operando. Corregido: solo se usan precios cuando la suma de
   todos los tramos ronda 1 y el precio ya se ha movido.
2. Corregido: en conjunto **pierde** (−5 % a −10 % por apuesta, deslizamiento 2 c).
3. Las **mínimas durante el día** ganan en la simulación (+26–41 %, todas las semanas, 43 de 47 ciudades,
   aguanta deslizamiento de 4 c) **pero no son ejecutables**: libros reales del 27-oct → diferencia
   mediana compra/venta 43 c y volumen mediano 7 $. El precio histórico es un punto medio ficticio.
4. Máximas (donde hay liquidez: diferencia 2–3 c, ~78 $ a menos de 3 c): pierden con previsiones de
   1–2 días de retraso; solo "durante el día y precio ≥ 20 c" sale algo positivo (+5–7 %, marginal).

Siguiente: reconstruir las previsiones tal como se publicaban cada 6 h (API de ejecuciones individuales
de Open-Meteo, GFS + ECMWF, 25 ciudades, 4 semanas) para igualar la frescura de datos de Bilberry.

## 27-oct: previsiones frescas (GFS + ECMWF directos de AWS, hora real de publicación) — nwp.py, frescas.py

- 360 ejecuciones (11-sep → 26-oct), 49 ciudades, 2.132 mercados de máxima.
- "Comprar cuando el modelo discrepa del precio" **pierde** (−9 % a −15 %): el mercado predice mejor que
  GFS+ECMWF en bruto a cualquier antelación (Brier 0,046 vs 0,055; diag.py).

## 27-oct: estrategia "reaccionar al cambio" — cambio.py  ★ primera señal positiva sólida

Cada hora (hh:10 UTC), si la probabilidad de nuestro modelo para un tramo cambia ≥ X respecto a la hora
anterior (nueva medición METAR o nueva ejecución del modelo), comprar en esa dirección y mantener.
El precio solo recoge parte del cambio en esa hora y sigue moviéndose después (lag.py).

| Regla | Apuestas (31 días) | Por apuesta, desliz. 2 c | Por apuesta, desliz. 3 c | Semanas en positivo |
|---|---|---|---|---|
| Δp ≥ 0,15 | 2.347 | +11,8 % | +9,0 % | 5/5 y 4/5 |
| Δp ≥ 0,20 | 1.821 | +17,1 % | +14,2 % | 5/5 |
| Δp ≥ 0,30 | 1.211 | +26,4 % | +23,4 % | 5/5 |

- Casi todo viene de **durante el día** (≤24 h antes del cierre); con más antelación no funciona.
- Usar precios de 10–20 min antes mejora mucho el resultado → **la velocidad importa**; el bot real
  debe actuar en cuanto llega la medición, no esperar a hh:10.
- Bilberry paga ~1,5–1,8 c sobre el precio histórico → el deslizamiento de 2–3 c es realista.
- Bilberry hace otra cosa: compra ~29 h antes (su propio modelo) y vende durante el día. Su ventaja y la
  nuestra no se solapan.

Riesgos pendientes: el precio histórico es un punto medio; solo una prueba en vivo con los precios reales
de compra (libro de órdenes) lo confirma. Siguiente paso: bot en sombra en tiempo real.
