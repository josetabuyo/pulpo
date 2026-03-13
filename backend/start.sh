#!/bin/bash
# Arrancar el backend Python (puerto 8000, no pisa el Node.js en 3000)
cd "$(dirname "$0")"
.venv/bin/uvicorn main:app --reload --port 8000 --host 0.0.0.0
