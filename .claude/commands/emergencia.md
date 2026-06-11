# /emergencia — Inicializar el sistema de monitoreo Pulpo

Sos el sistema de guardia de Pulpo (Emergencia On Going).
Ejecutá estos pasos en orden sin pedir confirmación:

## Paso 1 — Chequeo de estado actual

Corré estos dos comandos en paralelo:
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/bots`
- `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173`

Interpretación: backend UP = responde cualquier código ≠ "000". Frontend UP = responde 200.

## Paso 2 — Ver últimas líneas del log

```
tail -10 /Users/josetabuyo/Development/pulpo/_/monitor/backend.log
```

## Paso 3 — Activar el loop de monitoreo horario

Creá un CronCreate con:
- cron: `"7 * * * *"` (cada hora a los :07)
- recurring: true
- prompt (copiar verbatim):

```
MONITOREO PULPO — chequeo automático horario. Ejecutar sin pedir confirmación:

1. En paralelo: (a) curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/bots (b) curl -s -o /dev/null -w "%{http_code}" http://localhost:5173

2. Backend DOWN si resultado es "000" o comando falla. Frontend DOWN si resultado no es "200".

3. Si backend DOWN:
   a. Bash: lsof -i :8000 | grep LISTEN
   b. Si hay proceso que NO sea Pulpo (uvicorn de /Development/pulpo): Bash: say -v "Paulina" "Atención! El puerto 8000 está ocupado por otra aplicación. Pulpo no puede levantarse."
   c. Si el puerto está libre o el proceso es Pulpo caído: Bash (desde /Users/josetabuyo/Development/pulpo/_): ./start.sh back
   d. Bash: sleep 8
   e. Volver a chequear: curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/bots
   f. Si sigue DOWN: usar Agent con model="sonnet" con este prompt: "El backend de Pulpo en /Users/josetabuyo/Development/pulpo/_ está caído y no levantó con start.sh. Leé las últimas 60 líneas de monitor/backend.log, identificá la causa raíz y aplicá la corrección mínima necesaria. Si no podés resolverlo, reportá exactamente qué encontraste."
   g. Bash: say -v "Paulina" "Emergencia! Emergencia! El backend de Pulpo cayó y no pudo recuperarse solo. Requiere atención inmediata."

4. Si frontend DOWN:
   a. Bash (desde /Users/josetabuyo/Development/pulpo/_): ./start.sh front
   b. Bash: say -v "Paulina" "Alerta! El frontend de Pulpo estaba caído. Intentando levantar."

5. Si todo OK: no hacer nada, no emitir ningún texto ni mensaje.
```

## Paso 4 — Reportar al usuario

Mostrar un resumen claro:
- Backend: UP / DOWN
- Frontend: UP / DOWN  
- Últimas líneas relevantes del log (sesiones WA activas)
- Job ID del cron activo
- Instrucción: "Para restablecer este sistema en una sesión nueva, usar /emergencia"
