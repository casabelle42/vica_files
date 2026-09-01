#!/bin/bash
# Run the LAS-VICA MQTT relay on Vector/NUC with lab broker defaults.
# Usage: ./start_server.sh
# Optional overrides: VICA_MQTT_BROKER, VICA_MQTT_PORT, VICA_NUC_VERBOSE

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

export VICA_MQTT_BROKER="${VICA_MQTT_BROKER:-127.0.0.1}"
export VICA_MQTT_PORT="${VICA_MQTT_PORT:-1884}"

if [ -f "$HOME/LAS-VICA/Network/netvenv/bin/activate" ]; then
  source "$HOME/LAS-VICA/Network/netvenv/bin/activate"
fi

echo "VICA_MQTT_BROKER=$VICA_MQTT_BROKER"
echo "VICA_MQTT_PORT=$VICA_MQTT_PORT"

cd "$ROOT"
exec python3 server.py
