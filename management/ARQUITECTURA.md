# Arquitectura actual — Pulpo

## Stack

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│         React + Vite (panel admin)                  │
│         → consume API REST del backend               │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│                Backend Python                        │
│         FastAPI — API REST                          │
│         Orquestación de bots y sesiones             │
│         Playwright — automatización WA Web          │
│         python-telegram-bot — polling Telegram       │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│              Base de datos                           │
│              SQLite — data/messages.db               │
└─────────────────────────────────────────────────────┘
```

## Las capas

### Frontend — React + Vite
- Panel admin: login, dashboard, monitor de logs, connect QR
- Portal del cliente: `/connect` con QR para escanear
- Tests con Playwright (independientes del backend de bots)

### Backend Python — FastAPI
- API REST para el frontend y para tests
- Gestiona múltiples sesiones WA (una por número) vía Playwright
- Gestiona bot de Telegram vía python-telegram-bot
- Lógica de negocio: auto-reply, allowedContacts, horario
- Simulador integrado (`sim.py`) cuando `ENABLE_BOTS=false`

### WhatsApp — Playwright Python
- `launch_persistent_context` con perfil Chrome en `data/sessions/{número}/profile/`
- El perfil persiste entre reinicios — no pide QR salvo que la sesión expire
- Observer JS inyectado detecta mensajes nuevos en tiempo real
- Envío de mensajes en página temporal para no interrumpir el observer

### Telegram — python-telegram-bot
- Polling directo, integrado en el backend Python
- Sin proceso separado ni adaptador

### Base de datos — SQLite
- `data/messages.db` — tabla `messages` con todos los mensajes recibidos/enviados
- Auto-creada al arrancar si no existe
- Suficiente para la escala actual; migración a PostgreSQL es decisión de Etapa 4

## Worktrees y ambientes

| Worktree | Backend | Frontend | Modo |
|----------|---------|----------|------|
| `_` | 8000 | 5173 | Real — bots conectados (`ENABLE_BOTS=true`) |
| dev-1 | 8001 | 5174 | Simulado — sin bots reales |
| dev-2 | 8002 | 5175 | Simulado — sin bots reales |

El simulador replica el pipeline completo (mensajes, auto_reply, DB) sin browser ni conexiones reales. Permite desarrollar y testear sin arriesgar la sesión de producción.

## Decisiones de arquitectura tomadas

| Decisión | Resolución |
|----------|-----------|
| ¿Node.js o Python para WA? | Python + Playwright directamente. Sin adaptador Node.js. |
| ¿SQLite o PostgreSQL? | SQLite por ahora — migrar en Etapa 4 cuando haya deploy separado |
| ¿Frontend: SPA o SSR? | SPA (Vite + React) — suficiente para panel admin |
| ¿Cómo aislar ambientes de dev? | Git worktrees con puertos distintos y simulador |

## Lo que viene — planes separados

- `PLAN_IA_AGENTES.md` — integración de IA (LangGraph, Claude SDK)
- `PLAN_PRODUCCION.md` — deploy en servidor, PostgreSQL, WhatsApp Business API
- `PLAN_CONTACTOS.md` — contactos por empresa en DB
- `PLAN_WA_RECONNECT.md` — recuperar mensajes perdidos al reconectar

---

*Documento vivo. Refleja el estado actual de la arquitectura.*
