#!/bin/bash
# Expira conversaciones waiting_gate con más de 24 horas
# Llamar desde launchd una vez por día
curl -s -X POST "http://localhost:8000/api/flows/conversations/expire?max_age_hours=24" \
  -u "admin:${ADMIN_PASSWORD:-MonoLoco}" | logger -t pulpo-expire
