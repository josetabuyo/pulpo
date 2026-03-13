# Plan: Migración a Backend Python — Etapa 1

## Objetivo de esta etapa

Construir el backend Python mínimo con Telegram como primer canal real, sin romper lo que ya funciona en Node.js. Al terminar esta etapa, el bot de Telegram correrá 100% en Python y el backend estará listo para recibir eventos de WhatsApp.

---

## Por qué Telegram primero

- No depende de `whatsapp-web.js` ni de Node.js
- Es una API oficial — sin hacks, sin browser headless
- El código actual (`telegram.js`) es simple y fácil de reimplementar en Python
- Nos permite estrenar la arquitectura en un canal real, sin riesgo para WhatsApp

---

## Stack elegido

| Componente | Tecnología |
|-----------|-----------|
| Backend / API REST | **FastAPI** (Python 3.12+) |
| Bot Telegram | **python-telegram-bot** v21+ |
| Base de datos | **SQLite** (mismo archivo, `data/messages.db`) — SQLAlchemy como ORM |
| Servidor async | **uvicorn** |
| Variables de entorno | **python-dotenv** |

---

## Estructura del proyecto Python

```
backend/
├── main.py              # arranque FastAPI + uvicorn
├── config.py            # carga de .env / phones.json
├── db.py                # SQLAlchemy, modelos, funciones equivalentes al db.js actual
├── api/
│   ├── bots.py          # GET /api/bots, etc.
│   ├── messages.py      # GET /api/messages
│   └── contacts.py      # futuro: PLAN_CONTACTOS
├── bots/
│   ├── telegram_bot.py  # reemplaza telegram.js
│   └── whatsapp_adapter.py  # recibe eventos del Node.js adaptador (futuro)
└── requirements.txt
```

---

## Qué tiene que hacer el Telegram bot en Python

Comportamiento a replicar de `telegram.js`:
1. Escuchar mensajes entrantes
2. Verificar si el remitente es un contacto permitido (de `phones.json` → luego desde DB)
3. Responder con el mensaje automático configurado para ese bot
4. Registrar el mensaje en `data/messages.db` (tabla `messages`)
5. Ignorar mensajes anteriores al arranque del bot

Comportamiento nuevo (preparando el terreno de VISION):
- La lógica de "qué responder" vive en el backend, no en el adaptador
- El bot Telegram es un punto de entrada — el backend decide la respuesta

---

## Fases de implementación

### Fase 1 — Entorno Python
- `backend/` carpeta con `requirements.txt`
- FastAPI mínimo corriendo con `GET /health`
- Conexión a SQLite funcionando

### Fase 2 — Telegram bot en Python
- `telegram_bot.py` replicando el comportamiento de `telegram.js`
- Mismo resultado observable: responde a contactos permitidos, loguea en DB
- `telegram.js` queda apagado, el Python toma su lugar

### Fase 3 — API REST migrada
- Endpoints de `api.js` reimplementados en FastAPI
- El frontend puede apuntar a `localhost:8000` en lugar de `localhost:3000`
- `api.js` queda apagado

### Fase 4 — Adaptador WhatsApp
- `index.js` se convierte en adaptador puro: recibe mensajes WA → POST al backend Python
- El backend Python toma las decisiones y responde al adaptador
- Primera vez que WhatsApp y Telegram comparten la misma lógica de negocio

---

## Decisiones de diseño

### ¿SQLite o PostgreSQL desde el arranque?
**SQLite por ahora.** Mismo archivo que usa Node.js, sin romper nada. Migramos a PostgreSQL cuando el backend Python sea el único que escribe.

### ¿Cómo conviven Node.js y Python mientras migra?
- Cada componente tiene su turno: primero Telegram, luego API, luego WA adaptador
- No corren en paralelo haciendo lo mismo — cuando Python toma algo, Node.js lo apaga
- La DB es compartida (SQLite), así que los datos son los mismos

### ¿Cómo queda preparado para IA y agentes (VISION)?
- La función "decidir qué responder" estará en Python desde el día 1
- Hoy devuelve un string fijo; mañana puede invocar LangGraph
- El adaptador WA/Telegram solo transporta mensajes — la inteligencia es del backend

---

## Dependencias

- Python 3.12+ instalado
- Bot token de Telegram disponible en `phones.json` o `.env`
- `data/messages.db` existente (se crea al arrancar si no existe)

---

## Worktrees activos y cómo se relacionan

| Worktree | Rama | Foco |
|----------|------|------|
| `_` | `master` | Producción / estable |
| `fix-watchdog` | `fix-watchdog` | Estabilidad WA en Node.js (en paralelo) |
| `arch/python-backend` | `arch/python-backend` | Esta migración |

---

*Documento vivo. Se actualiza al avanzar cada fase.*
