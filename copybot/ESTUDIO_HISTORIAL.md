# Revisión independiente del estudio de copia (10-nov-2026)

Hecha en la sesión de Dirección, fuera de la sesión del copybot. Se reproduce sin red con
`python radar-memecoins/estudios/copia/historial.py`. Usa las 3.806 operaciones de 1 USD o más de la
cartera seguida entre el 9-ago y el 9-nov-2026 (600 tokens).

## 1. Cómo gana él
| Dato | Valor |
|---|---|
| Comprado en total | 2.071.940 USD |
| Resultado de los 505 tokens cerrados | +88.784 USD (**+4,3 % de lo comprado**) |
| Tokens ganadores | 221 de 505 (44 %) |
| Token típico (mediana) | −93 USD |
| 5 mejores / 5 peores tokens | +154.214 USD / −143.718 USD |
| Aún abierto (6 tokens) | 79.017 USD de coste |
| Por mes de cierre | ago −131.247 · sep +64.038 · oct +64.494 · nov +91.499 |

Su ventaja es fina y depende de pocos aciertos grandes. Un 4,3 % sobre lo comprado deja poco margen:
copiar cuesta comisión y peor precio en la compra **y** en la venta.

## 2. El «+17–22 % al mes» del README salió de un subconjunto favorable
Los 29 tokens de `seleccion.json` dejaron +62.917 USD de flujo neto (ventas menos compras). Todos los
demás, −27.414 USD. Además se midió en 30 días que fueron de los buenos. No sirve como expectativa.

## 3. Copia con 5.000 USD, todo el historial
Resultado final y, entre paréntesis, el peor momento. Columnas: cuánto peor que él se compra / se vende.
Comisión del 1 % por lado en todos los casos.

| Tope por token | 1 % / 1 % | 3 % / 3 % | 2 % / 7,5 % | 5 % / 5 % |
|---|---|---|---|---|
| Sin tope | +76 % (−61 %) | +28 % (−68 %) | −13 % (−76 %) | −16 % (−77 %) |
| 5 % | +93 % (−32 %) | +66 % (−37 %) | +44 % (−44 %) | +40 % (−44 %) |
| **10 %** | +94 % (−45 %) | +65 % (−51 %) | +41 % (−58 %) | +37 % (−59 %) |
| 15 % | +97 % (−52 %) | +66 % (−58 %) | +42 % (−66 %) | +37 % (−66 %) |
| 20 % | +93 % (−57 %) | +62 % (−63 %) | +36 % (−71 %) | +29 % (−72 %) |
| 30 % | +83 % (−61 %) | +51 % (−68 %) | −17 % (−76 %) | −21 % (−77 %) |

**Aviso sobre el nivel:** aquí las 6 posiciones abiertas se valoran a su último precio de operación.
`topes.py` las valora al precio actual de Jupiter y da cifras más bajas (+33 % con tope del 10 %, −8 % sin
tope). Fíate de la forma de la tabla, no de los números exactos.

Por tramos de un mes, empezando de cero en cada uno (tope 10 %, 3 % / 3 %):

| Tramo | Resultado | Peor momento | Sin tope |
|---|---|---|---|
| 9-ago → 9-sep | **−42 %** | −50 % | −59 % |
| 9-sep → 9-oct | +33 % | −7 % | +34 % |
| 9-oct → 9-nov | +70 % | −3 % | +63 % |

## 4. Conclusiones
1. **Tres meses son tres datos, y uno es −42 %.** Quien hubiera empezado en agosto habría perdido la mitad
   de la cuenta en un mes antes de ver ninguna ganancia.
2. **El tope por token sí aporta, y no está ajustado a medida.** Con 5 %, 10 % o 15 % sale parecido. Lo que
   hace es limitar el daño cuando él concentra mucho en un token que pierde. Casi todo su efecto viene de
   agosto; en octubre-noviembre apenas cambia nada.
3. **El precio de venta manda.** Sin tope, pasar de vender un 3 % peor a un 7,5 % peor convierte +28 % en −13 %.
4. **Una cartera, un periodo.** Se le eligió porque le iba bien: eso infla lo que se ve hacia atrás.
5. **Una simulación de pocos días no puede decir si copiarle es rentable** (eso cambia de −42 % a +70 % de
   un mes a otro). Solo puede decir si el bot consigue precios cercanos a los suyos.

## 5. Primeros datos del bot simulado
- 8–9 nov (configuración anterior): 22 operaciones; compras un 1,7 % peor que él (mediana) y ventas un 7,5 %
  peor; −25,69 USD sobre 166 USD comprados. Ese bot ignoraba ventas que llegaban tarde (corregido el 10-nov).
- Desde el 9-nov (`v2/`): 4 compras de un solo token, sin ventas todavía. Sin conclusión.

## 6. Condiciones para pasar a dinero real (acordadas el 10-nov-2026)
Se fijan antes de ver más datos. Deben cumplirse todas:

1. Al menos **4 semanas** de simulación, **100 ventas cerradas** y **30 tokens distintos**.
2. Precio medido frente al suyo (mediana): compras como mucho un **3 % peor**; ventas como mucho un **5 % peor**.
3. Resultado simulado **positivo** después de restar un 1 % por lado de comisiones.
4. Si la simulación cae más de un **30 %** en cualquier momento, no se pasa a real.
5. Empezar en real con **500 USD** que se puedan perder enteros. Subir solo tras 100 operaciones reales
   cuyo resultado se parezca al simulado.

Por la condición 1, el flujo simulado se alarga hasta el 8-dic-2026.
