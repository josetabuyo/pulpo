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

echo "════════════════════════════════════════"
echo "  Ambiente : $WORKTREE"
echo "  Backend  : http://localhost:${BACKEND_PORT}"
echo "  Frontend : http://localhost:${FRONTEND_PORT}"
echo "════════════════════════════════════════"

MODE="${1:-both}"

start_back() {
  echo "▶ Iniciando backend (puerto ${BACKEND_PORT})..."
  cd "$ROOT/backend" && exec ./start.sh
}

start_front() {
  echo "▶ Iniciando frontend (puerto ${FRONTEND_PORT})..."
  cd "$ROOT/frontend" && exec npm run dev
}

case "$MODE" in
  back)  start_back ;;
  front) start_front ;;
  both)
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
