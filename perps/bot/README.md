# Copybot simulado de perpetuos (Hyperliquid)

Copia en simulado a los 10 traders de `perps/v2/INFORME.md` (5 conservadores y 5 agresivos, 10% del capital cada uno), a 3x su tamaño proporcional desde el 19-nov (apalancamiento máx. 9x por porción).
Corre en GitHub Actions (`.github/workflows/perps-simulado.yml`) hasta el 8-dic-2026; los datos van a la rama
`perps-datos`, carpeta `v1/`:
- `operaciones.csv`: cada operación copiada (precio con deslizamiento, ganancia realizada, retraso).
- `resumen.csv`: capital total y de cada trader cada 10 min.
- `estado.json`: posiciones abiertas por trader.
Avisos al móvil por ntfy (mismo tema que el otro bot) al abrir/cerrar posiciones y un resumen diario.
Las posiciones que cada trader ya tenía al arrancar no se copian. No incluye funding.
