#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="${APP_NAME:-tcc-bridge}"
APP_USER="${APP_USER:-$(id -un)}"
APP_GROUP="${APP_GROUP:-$(id -gn)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
SERVICE_NAME="${SERVICE_NAME:-tcc-bridge}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONFIG_DIR="${CONFIG_DIR:-/etc/tcc-bridge}"
CONFIG_FILE="${CONFIG_FILE:-${CONFIG_DIR}/bots.toml}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

echo "[1/7] Checking OS"
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "22.04" ]]; then
    echo "warning: this script is intended for Ubuntu 22.04, current: ${PRETTY_NAME:-unknown}" >&2
  fi
fi

echo "[2/7] Installing system packages"
require_command apt-get
$SUDO apt-get update
$SUDO apt-get install -y python3 python3-venv python3-pip

echo "[3/7] Preparing runtime directories"
require_command "$PYTHON_BIN"
mkdir -p "${APP_DIR}"
mkdir -p "${APP_DIR}/logs"
mkdir -p "${CONFIG_DIR}"
touch "${APP_DIR}/.env"
if [[ ! -f "${CONFIG_FILE}" && -f "${APP_DIR}/bots.toml.example" ]]; then
  cp "${APP_DIR}/bots.toml.example" "${CONFIG_FILE}"
  echo "created ${CONFIG_FILE} from example"
fi

echo "[4/7] Installing Python dependencies"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[5/7] Installing systemd service"
TMP_SERVICE="$(mktemp)"
cat > "${TMP_SERVICE}" <<EOF
[Unit]
Description=TCC Bridge - Telegram Claude Code Bridge
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment=TCC_BRIDGE_CONFIG=${CONFIG_FILE}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/src/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF
$SUDO install -m 0644 "${TMP_SERVICE}" "${SERVICE_FILE}"
rm -f "${TMP_SERVICE}"

echo "[6/7] Reloading and starting service"
$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}"
$SUDO systemctl restart "${SERVICE_NAME}"

echo "[7/7] Post-check"
$SUDO systemctl --no-pager --full status "${SERVICE_NAME}" || true

if ! command -v claude >/dev/null 2>&1; then
  echo
  echo "warning: 'claude' command not found. Install Claude Code CLI and log in before using the service."
fi

echo
echo "deployment complete"
echo "next steps:"
echo "1. edit ${CONFIG_FILE}"
echo "2. if needed, edit ${APP_DIR}/.env"
echo "3. inspect logs with: sudo journalctl -u ${SERVICE_NAME} -f"
