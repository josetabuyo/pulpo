#!/bin/bash
# Rotación semanal de logs. Archiva con semana ISO (YYYY-WXX), borra > 8 semanas.
# Corre desde cualquier directorio; usa la raíz del worktree _ siempre.

DIR="/Users/josetabuyo/Development/pulpo/_/monitor"
WEEK=$(date +%G-W%V)   # ej: 2026-W22
KEEP=8                  # semanas a conservar

rotate_one() {
    local log="$DIR/$1"
    local base="$DIR/$2"   # prefijo del archivo de archivo, sin extensión
    [ -s "$log" ] || return
    cp "$log" "${base}.${WEEK}.log"
    : > "$log"
}

rotate_one "backend.log"  "backend"
rotate_one "frontend.log" "frontend"

# Borrar archivos con patrón YYYY-WXX.log más viejos de $KEEP semanas
find "$DIR" -maxdepth 1 -name "*.log" \
    -not -name "backend.log" \
    -not -name "frontend.log" \
    -not -name "fastapi.log" \
    -not -name "monitor.log" \
    -not -name "ngrok.log" \
    -not -name "fb_cookies.log" \
    -mtime "+$((KEEP * 7))" \
    -delete

echo "$(date '+%Y-%m-%d %H:%M') — rotación completa (semana $WEEK)" >> "$DIR/rotate.log"
