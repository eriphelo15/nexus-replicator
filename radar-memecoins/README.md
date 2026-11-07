# Radar de memecoins (Solana)

Movido desde `An-lisis-cuantitativo` el 2026-11-07.

- `RADAR.md`: cómo funciona el radar (vigía, escaneo, supervivientes, motor de salida).
- `ESTUDIO_GIGANTES.md`: estudio de las memecoins que subieron miles de %.
- `estudios/gigantes/`: scripts y datos del estudio.
- `estudios/backtest/`: backtest intradía de "despertares" (velas de 1 h de GeckoTerminal).
- `workflow-pausado/radar.yml`: el flujo de GitHub Actions, **pausado**. Para activarlo hay que
  copiarlo a `.github/workflows/` y añadir el secreto `NTFY_TOPIC` en este repositorio.

Los datos recogidos por el radar (27-29 sep 2026) siguen en la rama `radar-datos` de
`An-lisis-cuantitativo`.
