#!/bin/bash
# Reinicia el backend.
# Si launchd gestiona el servicio (KeepAlive), solo hay que matar uvicorn —
# launchd lo reinicia solo. Arrancar manualmente causaría conflicto de puerto.
ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE="com.josetabuyo.pulpo"

if launchctl list | grep -q "$SERVICE"; then
    launchctl kickstart -k "gui/$(id -u)/$SERVICE"
    echo "Backend reiniciado vía launchd."
else
    "$ROOT/stop-backend.sh"
    sleep 3
    "$ROOT/start.sh" back
fi
