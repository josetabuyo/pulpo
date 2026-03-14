#!/bin/bash
# Arrancar el backend Python (puerto 8000, no pisa el Node.js en 3000)
cd "$(dirname "$0")"
# Busca .venv local o usa el del directorio principal (_/backend)
VENV=".venv"
if [ ! -d "$VENV" ]; then
  VENV="/Users/josetabuyo/Development/whatsapp_bot/_/backend/.venv"
fi
"$VENV/bin/uvicorn" main:app --reload --port 8000 --host 0.0.0.0
