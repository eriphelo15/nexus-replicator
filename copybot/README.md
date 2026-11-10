# Bot de copia (Solana)

Replica las compras y ventas de las carteras de `config.json` con 1-3 s de retraso, vía Jupiter.
Estudio previo: `../radar-memecoins/estudios/copia/` (copiar a bystevenr a 1-30 s conservaba
~+17-22% al mes en sus 29 tokens principales, frente a su +46%).

## Cómo decide
- **Compra:** el importe de su compra × `capital_usd / capital_referencia_usd` × `peso`.
  `capital_referencia_usd` es su exposición máxima (bystevenr: $259K), así que el factor es
  proporcional (con $5K, ~1.9%). Tope por token `max_por_token_usd` = **10% del capital**: en sus
  3 meses (ago-nov) la copia sin tope perdía un 8% y con tope del 10% ganaba un 33%
  (`../radar-memecoins/estudios/copia/topes.py`). No compra si el impacto en
  precio supera `impacto_max_pct` o si se alcanzó `perdida_dia_max_usd`.
- **Venta:** vende el mismo % de la posición que vende él (todo si él se queda a cero). Sus ventas se
  copian siempre, aunque lleguen tarde. Si una venta no sale (sin cotización o sin confirmar), queda en
  `ventas_pendientes` y se reintenta sola (15 s, 30 s… hasta cada 5 min), con aviso al móvil.
- Ignora **compras** suyas de hace más de `retraso_max_s` segundos (p. ej., tras un corte).
- Deslizamiento máximo: `slippage_bps` en compras (3 %) y `slippage_venta_bps` en ventas (10 %: lo
  importante es salir). Con `comprobar_antes` el nodo simula la orden antes de enviarla.

## Modos
- `"modo": "simulado"`: cotiza en Jupiter en el momento real y anota en `datos_bot/operaciones.csv`
  qué habría hecho y a qué precio frente al suyo, sin enviar nada.
- `"modo": "real"`: firma y envía. Necesita la clave privada de una **cartera nueva solo para el
  bot** en la variable `BOT_CLAVE_PRIVADA` (archivo `.env` del servidor, nunca en el repositorio),
  con USDC para operar y ~0.1 SOL para comisiones.

## Desde el móvil (ntfy)
Avisos de cada operación en el tema `NTFY_TOPIC`. Órdenes publicando en `NTFY_ORDENES` (si no se
define, `<NTFY_TOPIC>-bot`): `parar` (no compra más; sigue copiando ventas), `seguir`, `vender todo`, `estado`.

Seguridad de las órdenes: en ntfy.sh cualquiera que conozca el nombre de un tema puede leerlo y publicar.
- `NTFY_CLAVE`: si existe, cada orden debe empezar por ella (`miclave vender todo`).
- `NTFY_TOKEN`: token de ntfy para un tema reservado (solo tú lees y publicas). Es la opción segura.
- **En modo real, sin `NTFY_CLAVE` ni `NTFY_TOKEN` el bot no acepta órdenes.** La clave sola viaja por el
  mismo tema: sirve contra quien adivine el nombre, no contra quien ya lo esté leyendo.

## Antes de pasar a real
Pendiente: al menos 100 operaciones en simulado con resultado positivo después de costes. Los primeros
datos (8–9 nov, 22 operaciones) dieron −25,69 USD sobre 166 USD comprados.

Pruebas sin red: `python -m pytest copybot/test_bot.py`.

## Instalación en el servidor (Ubuntu 24.04)
```bash
sudo apt update && sudo apt install -y python3-venv git
sudo git clone https://github.com/eriphelo15/nexus-replicator /opt/repo
sudo cp -r /opt/repo/copybot /opt/copybot && cd /opt/copybot
sudo python3 -m venv venv && sudo venv/bin/pip install -r requirements.txt
sudo cp config.ejemplo.json config.json      # poner aquí la URL de Helius
sudo nano .env                                # NTFY_TOPIC=...  (en real: BOT_CLAVE_PRIVADA=... y NTFY_CLAVE=... o NTFY_TOKEN=...)
sudo chmod 600 .env
sudo cp copybot.service /etc/systemd/system/ && sudo systemctl enable --now copybot
journalctl -u copybot -f                      # ver lo que hace
```
