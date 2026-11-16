# Traders de Hyperliquid para copiar — búsqueda v2 (16-nov-2026)

Filtros (`buscar.py`): clasificación completa (47,755) → capital >= $10K, ganancia histórica >= $30K, ROI >= 50%, activo
este mes (3,526) → >= 6 meses, >= 70% meses positivos, peor caída <= 40%, ganando en 90 días (158) → >= 20 cierres y
duración mediana >= 1 h (40 simulados; 66 scalpers y 52 con pocas operaciones descartados).
Copia simulada: $10K, apalancamiento máx. 3x, 90 días, sin reglas de fondeo, sin funding.

## Cartera propuesta (10)
| Perfil | Trader | Copia 90 d | Caída copia | Meses + | Duración |
|---|---|---|---|---|---|
| Conservador | 0x8bae3527e5a33fa0cf184f37bc112d071463ab6d | +71% (v1) | 9% | 14/17 | ~9 días |
| Conservador | 0xca7cd4c133338df50398d576c8cae48be76399a2 | +40% | 12% | 28/37 | 25 h |
| Conservador | 0x03ef8f736498047c3349bb2c18311d1bb4a79054 | +35% | 5% | 8/11 | 26 h |
| Conservador | 0x69b05701f8175c276ecd0138387a197948e240bb | +27% | 7% | 14/18 | 31 h |
| Conservador | 0x2312171890250347dbf1b082bdf7950504909e92 | +20% | 5% | 29/40 | ~5 días |
| Agresivo | 0xd46979f07f5d1e86ae2dcc5e6e0f3af5fe270471 | +106% | 26% | 13/15 | 16 h |
| Agresivo | 0xf53cab0c6f25f48f985d1e2c40e03fc7c1963364 | +85% | 22% | 26/36 | ~10 días |
| Agresivo | 0xf83858e57d9f804f5ca1603bce82558119aeac7b | +70% | 24% | 26/35 | 18 h |
| Agresivo | 0x838d8e13ec1010e7851b3dc333699db885f2520c | +46% | 36% | 6/8 | 2 h |
| Agresivo | 0x92ec1dd166d6271a4f2780e8223d00f4ba3d3f44 | +25% | 18% | 18/23 | 12 h |

0x8bae quedó fuera del filtro por 19 cierres (mínimo 20), pero se incluye: mantiene posiciones días y ganó $12.8M en 17 meses.
Ranking completo en `resultados.json`.
