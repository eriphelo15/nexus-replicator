#!/usr/bin/env bash
# Instala el bot en sombra en un servidor Ubuntu 24.04 (ejecutar como root).
#   curl -fsSL https://raw.githubusercontent.com/eriphelo15/nexus-replicator/prediction-markets/prediction_bot/sombra/instalar.sh | bash
set -euo pipefail
echo ">> Instalando paquetes del sistema…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3-venv python3-pip > /dev/null

echo ">> Descargando el bot…"
mkdir -p /opt/bot
if [ -d /opt/bot/repo/.git ]; then
  git -C /opt/bot/repo pull -q
else
  git clone -q --depth 1 -b prediction-markets https://github.com/eriphelo15/nexus-replicator /opt/bot/repo
fi

echo ">> Preparando Python…"
python3 -m venv /opt/bot/venv
/opt/bot/venv/bin/pip install -q --upgrade pip
/opt/bot/venv/bin/pip install -q requests numpy eccodes

mkdir -p /opt/bot/datos /opt/bot/web
[ -f /opt/bot/datos/web_secreto ] || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n' > /opt/bot/datos/web_secreto

cat > /etc/systemd/system/bot.service <<'EOF'
[Unit]
Description=Bot temperatura (modo sombra)
After=network-online.target
[Service]
WorkingDirectory=/opt/bot/repo/prediction_bot/sombra
Environment=BOT_DATA=/opt/bot/datos BOT_WEB=/opt/bot/web
ExecStart=/opt/bot/venv/bin/python bot.py
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/bot-web.service <<'EOF'
[Unit]
Description=Pagina de resultados del bot
After=network-online.target
[Service]
ExecStart=/usr/bin/python3 -m http.server 80 --directory /opt/bot/web
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable -q --now bot.service bot-web.service
systemctl restart bot.service

IP=$(curl -fsS https://api.ipify.org || hostname -I | awk '{print $1}')
echo
echo "=============================================================="
echo " LISTO. El bot está funcionando en modo sombra (sin dinero)."
echo " La primera vez descarga ~35 días de datos (30-60 min)."
echo
echo " Tu página de resultados (guárdala en el iPhone):"
echo "   http://$IP/$(cat /opt/bot/datos/web_secreto)/"
echo "=============================================================="
