#!/bin/bash
# Detiene el frontend (Vite dev server) en el puerto configurado en .env (default 5173)
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/.env" 2>/dev/null
PORT="${FRONTEND_PORT:-5173}"
PID=$(lsof -ti :"$PORT" 2>/dev/null)
if [ -n "$PID" ]; then
    kill -TERM $PID
    echo "Frontend (PID $PID, puerto $PORT) detenido."
else
    echo "No hay proceso en el puerto $PORT."
fi
