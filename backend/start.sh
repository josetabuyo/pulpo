#!/bin/bash
# Arrancar el backend Python
# El puerto se toma de BACKEND_PORT en el .env del worktree (raíz del repo)
cd "$(dirname "$0")"

# Cargar .env desde la raíz del worktree (un nivel arriba de backend/)
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"

# Busca .venv local o usa el del directorio principal (_/backend)
VENV=".venv"
if [ ! -d "$VENV" ]; then
  VENV="/Users/josetabuyo/Development/pulpo/_/backend/.venv"
fi

echo "▶ Backend arrancando en http://localhost:${BACKEND_PORT}"

# En producción (ENABLE_BOTS=true) no usar --reload — evita recargas accidentales
# que matan las sesiones de WhatsApp Web. En worktrees de dev (ENABLE_BOTS=false)
# --reload es útil para iterar rápido sin consecuencias.
if [ "${ENABLE_BOTS}" = "true" ]; then
  "$VENV/bin/uvicorn" main:app --port "$BACKEND_PORT" --host 0.0.0.0
else
  "$VENV/bin/uvicorn" main:app --reload --port "$BACKEND_PORT" --host 0.0.0.0
fi
