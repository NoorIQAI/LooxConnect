#!/usr/bin/with-contenv bashio
set -euo pipefail

echo "Logging: Starting add-on NoorIQ Loox Connect at $(date)---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------"

IOTHUB_DEVICE_CONNECTION_STRING="$(bashio::config 'iothub_device_connection_string' || true)"
if bashio::var.is_empty "${IOTHUB_DEVICE_CONNECTION_STRING}"; then
  bashio::log.fatal "Logging: Missing iothub_device_connection_string in add-on configuration (Configurations tab)."
  bashio::exit.nok
fi

export IOTHUB_DEVICE_CONNECTION_STRING
export IOTHUB_METHOD_NAME="ha.call"
export HA_WS_URL="ws://supervisor/core/websocket"

exec /venv/bin/python -u /app/main.py