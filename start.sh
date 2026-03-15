#!/bin/bash
# ============================================================
# start.sh — Levanta back + front de ESTE worktree
#
# Uso:
#   ./start.sh          # usa puertos del .env local
#   ./start.sh back     # solo backend
#   ./start.sh front    # solo frontend
#
# Cada worktree tiene su propio .env con BACKEND_PORT y FRONTEND_PORT.
# Nunca mezcles puertos entre worktrees: cada ambiente es independiente.
# ============================================================

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/.env"

# Cargar .env
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "⚠️  No se encontró .env — copiá .env.example y configurá los puertos"
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
WORKTREE="$(basename "$ROOT")"

# Modo automático: _ es producción, cualquier otro worktree es simulado
if [ "$WORKTREE" = "_" ]; then
  export ENABLE_BOTS=true
  MODE_LABEL="real (bots conectados)"
else
  export ENABLE_BOTS=false
  MODE_LABEL="simulado (sin bots reales)"
fi

echo "════════════════════════════════════════"
echo "  Ambiente : $WORKTREE"
echo "  Modo     : $MODE_LABEL"
echo "  Backend  : http://localhost:${BACKEND_PORT}"
echo "  Frontend : http://localhost:${FRONTEND_PORT}"
echo "════════════════════════════════════════"

LOG_DIR="$ROOT/monitor"
mkdir -p "$LOG_DIR"

BACK_LOG="$LOG_DIR/backend.log"
FRONT_LOG="$LOG_DIR/frontend.log"

MODE="${1:-both}"

start_back() {
  echo "▶ Backend → $BACK_LOG"
  cd "$ROOT/backend" && ./start.sh >> "$BACK_LOG" 2>&1
}

start_front() {
  echo "▶ Frontend → $FRONT_LOG"
  cd "$ROOT/frontend" && npm run dev >> "$FRONT_LOG" 2>&1
}

case "$MODE" in
  back)  start_back ;;
  front) start_front ;;
  both)
    echo ""
    echo "  Logs en vivo:"
    echo "    tail -f $BACK_LOG"
    echo "    tail -f $FRONT_LOG"
    echo ""
    trap 'kill %1 %2 2>/dev/null' EXIT
    start_back &
    start_front &
    wait
    ;;
  *)
    echo "Uso: $0 [back|front|both]"
    exit 1
    ;;
esac
