#!/bin/bash
# Run the LAS-VICA Host GUI with lab MQTT broker defaults.
# Usage: ./start_host.sh
# Optional overrides: VICA_MQTT_BROKER, VICA_MQTT_PORT

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/Host/gui/s1_start_app.py"

# Lab broker defaults — only set when unset (do not clobber overrides).
# Lab broker port (matches Host Python defaults on this branch).
export VICA_MQTT_BROKER="${VICA_MQTT_BROKER:-10.148.1.35}"
export VICA_MQTT_PORT="${VICA_MQTT_PORT:-1884}"

echo "VICA_MQTT_BROKER=$VICA_MQTT_BROKER"
echo "VICA_MQTT_PORT=$VICA_MQTT_PORT"
echo "Starting Host GUI: $APP"

cd "$ROOT"
exec python3 "$APP"
