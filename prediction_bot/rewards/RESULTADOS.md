# Vigilancia de premios por liquidez en Polymarket (7–12 oct 2026)

## Conclusión

**No hay pruebas suficientes para pasar a dinero real, y lo poco que se pudo medir apunta en contra.**

## Qué pasó con la vigilancia

La vigilancia debía tomar una foto cada 4 horas (unas 30 fotos). Las ejecuciones programadas
se dispararon, pero la sesión que debía procesarlas estuvo reiniciándose y **no llegó a
ejecutarlas**. Solo hay 3 fotos válidas: 7-oct 05:49, 7-oct 08:51 y 12-oct 12:53 (UTC).

## Lo que sí se puede afirmar

| Medida | 7-oct | 12-oct |
|---|---|---|
| Premio total repartido por Polymarket | ~166.000 $/día | ~188.000 $/día |
| Mercados candidatos donde un nuevo participante se llevaría ≥50 % del premio | 42 (≈2.600 $/día) | **20 (≈1.300 $/día)** |
| Cuota mediana que se llevaría un nuevo participante | 3–4 % | **1 %** |

1. **La competencia aumentó**: los huecos con poca competencia se redujeron a la mitad en 5 días.
2. **El único tramo medido con rigor salió negativo**: en 3 horas (7-oct), la cartera de 30 mercados
   habría cobrado 97 $ de premio y perdido 235 $ por órdenes ejecutadas por operadores mejor
   informados → **−138 $**.
3. **Los mercados rotan muy rápido**: de los 30 elegidos el 7-oct, solo 4 seguían con premio el 12-oct.
   Un bot tendría que cambiar de mercados constantemente.

El tramo de 5 días (7-oct → 12-oct) da +261 $, pero **no es fiable**: con una foto cada 5 días el
programa solo ve las pérdidas por ejecución de las últimas 6 horas y no las de los 5 días.

## Recomendación sobre el paso 2 (prueba con 300–500 $)

**No hacerla todavía.** Si se quiere seguir:
- Repetir la vigilancia de forma fiable (por ejemplo con GitHub Actions) durante 7 días, o
- Hacer una prueba real muy pequeña (100–200 $) asumiendo que lo más probable es perder parte.

## Cómo reproducirlo

```bash
python vigilar.py   # toma una foto (≈1,5 min)
python evaluar.py   # evalúa todas las fotos sin mirar el futuro
```
