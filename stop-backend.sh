#!/bin/bash
# Detiene el backend en el puerto configurado en .env (default 8000)
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/.env" 2>/dev/null
PORT="${BACKEND_PORT:-8000}"
PID=$(lsof -ti :"$PORT" 2>/dev/null)
if [ -n "$PID" ]; then
    kill -TERM $PID
    echo "Backend (PID $PID, puerto $PORT) detenido."
else
    echo "No hay proceso en el puerto $PORT."
fi
