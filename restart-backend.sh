#!/bin/bash
# Reinicia el backend: detiene el proceso actual y lanza uno nuevo.
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/stop-backend.sh"
sleep 3
"$ROOT/start.sh" back
