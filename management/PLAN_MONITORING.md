# Plan: Panel de Monitoring — Log Viewer + Alertas

## Estado
✅ **Completado** — mergeado a master en commit `813ae97`

---

## Qué se construyó

### Botón "📊 Monitor" en el dashboard admin
- Visible en el header junto a Refresh y Salir
- Badge rojo con conteo de alertas activas

### Live Log Viewer
- Polling cada 2s a `GET /api/logs/latest` (se optó por polling en vez de SSE para compatibilidad con el header `x-password` que EventSource no soporta)
- Color-coded: ERROR/Traceback → rojo, WARNING → naranja, 200 OK/restored → verde, getUpdates → azul
- Auto-scroll al fondo (se desactiva si el usuario scrollea manualmente)
- Filtro de texto en tiempo real
- Botón Pausar / Reanudar

### Sparklines SVG
- req/min y err/min — últimos 10 minutos, calculados en cliente desde timestamps del log
- SVG puro, sin librerías externas

### Sistema de Alertas
- Detecta: `Traceback`, `HTTP/1.1 5xx`, `session lost`
- Badge rojo en el botón del dashboard
- Panel de alertas con las últimas líneas que dispararon la alerta
- Botón "Descartar"

---

## Archivo de configuración: `monitoring.json`

En la raíz del proyecto (trackeado en git).

```json
{
  "log_sources": {
    "backend": "monitor/backend.log",
    "frontend": "monitor/frontend.log"
  },
  "highlight_patterns": [...],
  "alert_patterns": [...],
  "display": {
    "max_lines": 500,
    "default_source": "backend",
    "refresh_interval_ms": 2000
  }
}
```

Los paths son relativos a la raíz del proyecto.

---

## Arquitectura implementada

### Backend: `backend/api/logs.py`

```
GET /api/logs/latest?source=backend&lines=200   → últimas N líneas como lista
GET /api/logs/stream?source=backend             → SSE (tail -f)
```

Ambos requieren `x-password` (admin). Lee paths desde `monitoring.json`.

### Frontend: `frontend/src/components/MonitorPanel.jsx`

- Hook interno `useLogPoller` — fetch cada 2s, buffer de 500 líneas, detección de alertas
- Drawer lateral (~45vw, fondo oscuro `#1a1a1a`)
- Tabs backend / frontend

### Cambio en `sim.py`

Agregado logging de mensajes del simulador:
- `[sim] MSG ← {from_name} ({from_phone}) → {session_id}: {text}`
- `[sim] REPLY → {session_id}: {reply[:80]}`

---

## Decisiones técnicas

| Decisión | Razonamiento |
|---|---|
| Polling en vez de SSE | EventSource no soporta headers custom; polling 2s es suficiente |
| Sin librerías de gráficos | SVG puro, cero dependencias |
| Sin DB de métricas | Calculado on-the-fly desde el log en memoria |
| monitoring.json trackeado | Es config de infra, no secrets |

---

## Tests

- `backend/tests/test_logs.py` — 9 tests (auth, source inválido, contenido)
- `frontend/tests/monitor.spec.cjs` — 13 tests Playwright (drawer, log, filtro, pausa, sim→log)
