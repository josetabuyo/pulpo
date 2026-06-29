#!/bin/bash
# Wrapper para launchd: carga variables de .env antes de iniciar el backend.
# El .env (gitignoreado) contiene ADMIN_PASSWORD, BACKEND_PORT, etc.
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$DIR/.env"
  set +a
fi
exec "$DIR/.venv-pulpo/bin/pulpo" server ui --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
