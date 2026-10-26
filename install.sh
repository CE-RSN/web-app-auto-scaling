#!/bin/bash
# =============================================================================
# Instala la web de demostración de Auto Scaling como servicio del sistema.
# Pensado para Amazon Linux 2023. Ejecútalo como root:
#
#   sudo bash install.sh
#
# Se puede ejecutar varias veces: si ya estaba instalada, la actualiza.
# =============================================================================
set -euo pipefail

APP_DIR=/opt/web-app-auto-scaling
APP_USER=webapp
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta el script como root: sudo bash install.sh" >&2
  exit 1
fi

echo "==> 1/5 Instalando Python"
dnf install -y -q python3.11 python3.11-pip || dnf install -y -q python3 python3-pip
PYTHON="$(command -v python3.11 || command -v python3)"
echo "    Usando $("$PYTHON" --version)"

echo "==> 2/5 Copiando la aplicación a $APP_DIR"
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  mkdir -p "$APP_DIR"
  cp -r "$SRC_DIR"/. "$APP_DIR"/
fi

echo "==> 3/5 Creando el usuario $APP_USER (la web no se ejecuta como root)"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --home-dir "/var/lib/$APP_USER" --shell /sbin/nologin "$APP_USER"

echo "==> 4/5 Creando el entorno virtual e instalando dependencias"
"$PYTHON" -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> 5/5 Registrando el servicio web-app en systemd"
install -m 644 "$APP_DIR/web-app.service" /etc/systemd/system/web-app.service
systemctl daemon-reload
systemctl enable web-app
systemctl restart web-app

for _ in $(seq 1 20); do
  if curl -fs http://localhost/health >/dev/null; then
    echo "✅ Web funcionando en el puerto 80 (comprobado en http://localhost/health)"
    exit 0
  fi
  sleep 1
done

echo "❌ La web no responde. Revisa el servicio con: journalctl -u web-app -n 50" >&2
exit 1
