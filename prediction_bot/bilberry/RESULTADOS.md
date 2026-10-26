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
