#!/bin/bash
# Run the LAS-VICA edge MQTT client with correct device identity and broker defaults.
# Usage: ./start_client.sh
# Optional overrides: VICA_DEVICE_NAME, VICA_MQTT_BROKER, AUTO_START_CONTAINER=1

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

export VICA_DEVICE_NAME="${VICA_DEVICE_NAME:-$(hostname)}"
export VICA_EDGE_NAME="${VICA_EDGE_NAME:-$VICA_DEVICE_NAME}"
# Default matches current lab broker on Vector (eno1). Override if NUC returns.
export VICA_MQTT_BROKER="${VICA_MQTT_BROKER:-10.148.1.35}"
export VICA_MQTT_PORT="${VICA_MQTT_PORT:-1884}"
export AUTO_START_CONTAINER="${AUTO_START_CONTAINER:-0}"

if [ -f "$HOME/cosmos/bin/activate" ]; then
  # thor1-style Jetson (conda cosmos env)
  source "$HOME/cosmos/bin/activate"
elif [ -f "$ROOT/.venv/bin/activate" ]; then
  # thor2-style Jetson (project venv)
  source "$ROOT/.venv/bin/activate"
fi

cd "$ROOT"
exec python3 client.py
