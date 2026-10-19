# Prueba histórica: previsiones meteorológicas contra Kalshi

**Fecha:** 2026-10-07 · **Datos:** 289 días (oct-2025 → oct-2026), 7 ciudades
(NY, Chicago, Miami, Austin, Denver, Los Ángeles, Filadelfia), 15.582 mercados de
temperatura máxima diaria, 7 modelos meteorológicos (ECMWF, GFS, NBM, ICON, GEM,
UKMO, JMA).

## Conclusión

**No hay ventaja explotable.** El mercado de Kalshi predice la temperatura mejor
que una combinación de 7 modelos meteorológicos públicos corregidos por sesgo.

| Prueba | Precisión modelo / mercado (Brier, menor = mejor) | Resultado por contrato | ¿Fiable? |
|---|---|---|---|
| **Honesta**: víspera, solo datos ya publicados | 0,133 / **0,117** | **−4 céntimos** (pierde un 9–12 % de lo invertido) | Sí, la pérdida es muy clara (t ≈ −7) |
| **Con ventaja injusta**: previsión algo más fresca de la que existiría en la realidad | 0,125 / **0,117** | entre −0,3 y +2 céntimos | No: indistinguible de cero |
| **Mismo día por la mañana** | 0,165 / **0,131** | **−3 céntimos** | Sí, pierde |

El mercado ya incorpora las previsiones públicas (y probablemente otras mejores).
Ni dándole al modelo información que en la práctica no tendría consigue ganar.

## El único resquicio: comprar "NO" en tramos muy improbables

Los tramos que cotizan entre 3 y 6 céntimos ganan algo menos de lo que su precio
indica (sesgo favorito-sorpresa). Comprar "NO" en ellos dio **+0,9 céntimos por
contrato** (≈1 % por operación, a 1–2 días vista; 1.743 operaciones, 3 de 13 meses
en negativo).

Por qué **no** lo considero una oportunidad sólida:
- Salió al probar 8 rangos de precio; los tramos vecinos (0–3 y 6–10 céntimos) no
  lo confirman. Puede ser casualidad.
- Arriesgas ~96 céntimos para ganar ~1. Una racha de sorpresas borra meses de ganancia.
- Poca liquidez: mediana de 57 contratos negociados por hora en ese momento.
- Orden de magnitud: con 100 contratos por operación serían unos 1.500 $ al año,
  y solo si el efecto es real y no se cierra.

## Cómo reproducirlo

```bash
python fetch_kalshi.py --desde 2025-10-01   # ~45 min, caché en data/
python fetch_forecasts.py                   # ~15 min
python backtest.py                          # informe completo
```

Garantías contra hacer trampas sin querer:
- Previsiones archivadas tal como estaban publicadas antes de cada decisión.
- Sesgo y error de cada modelo aprendidos solo con días anteriores (walk-forward).
- Se compra al precio de venta real del mercado (ask), con comisión de Kalshi.
- Intervalos de confianza remuestreando días completos.
