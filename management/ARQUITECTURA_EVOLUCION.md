# Evolución de Arquitectura — Pulpo

## El problema de fondo

El backend actual está en Node.js. Funciona para lo que hacemos hoy (bots de mensajería, respuesta automática, SQLite). Pero la visión es construir agentes con IA — y el ecosistema de IA es Python-first:

- **LangChain / LangGraph** — orquestación de agentes
- **LlamaIndex** — RAG e indexación de documentos
- **Claude SDK, OpenAI SDK** — mejor soporte y ejemplos en Python
- **Playwright** — automatización de browser, integrable con agentes Python
- **FastAPI** — backend moderno, async, ideal para una plataforma SaaS

Seguir construyendo en Node.js nos pone en deuda técnica el día que activemos el feature de IA.

---

## La arquitectura propuesta

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│         React + Vite (panel admin)                  │
│         → consume API REST / WebSocket               │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│                Backend Python                        │
│         FastAPI — API REST + WebSocket               │
│         Orquestación de bots y agentes               │
│         LangGraph para flujos de IA (futuro)         │
│         Playwright para automatizaciones web          │
└───────┬──────────────────────────┬───────────────────┘
        │                          │
┌───────▼───────┐        ┌─────────▼─────────┐
│  Adaptador WA │        │  Adaptador Telegram│
│  (Node.js)    │        │  (Python-telegram- │
│  whatsapp-    │        │   bot o Telethon)  │
│  web.js       │        └───────────────────┘
└───────────────┘
        │
┌───────▼───────────────────────────────────────────┐
│              Base de datos                         │
│   PostgreSQL (producción) / SQLite (desarrollo)    │
└───────────────────────────────────────────────────┘
```

---

## Las capas

### Frontend — React + Vite
- Panel admin de la plataforma
- Gestión de empresas, bots, contactos, conversaciones
- No cambia la tecnología actual, pero se organiza mejor

### Backend Python — FastAPI
- Reemplaza el `api.js` + `index.js` actual
- Recibe eventos de los adaptadores (mensaje entrante) y decide qué hacer
- Orquesta la respuesta: mensaje fijo, menú, agente IA, o acción en browser
- Persiste en DB

### Adaptador WhatsApp — Node.js (transitorio)
- `whatsapp-web.js` seguirá siendo Node.js por ahora — no hay alternativa confiable en Python para WhatsApp no-oficial
- El adaptador habla con el backend Python vía HTTP o WebSocket
- Es una capa fina: recibe mensajes → los manda al backend; recibe órdenes del backend → los manda por WhatsApp
- A futuro: reemplazable por WhatsApp Business API oficial (sin Node.js)

### Adaptador Telegram — Python
- `python-telegram-bot` o similar
- Se integra directo al backend Python, sin adaptador separado

### Playwright (Python)
- Corre dentro del backend Python
- Maneja sesiones de Chrome para automatizaciones web
- Reemplaza el uso implícito de Puppeteer que hace whatsapp-web.js para el resto de features

---

## Plan de migración

### Etapa 0 — No romper nada ✅
- Node.js estabilizado, arquitectura documentada

### Etapa 1 — Backend Python mínimo + React frontend ✅ (2026-03-13)
- FastAPI + python-telegram-bot reemplazan `api.js` y `telegram.js`
- Frontend React (Vite): login, dashboard, connect QR
- Tests de Playwright para el flujo de login y proxy
- Todo mergeado a master

### Etapa 2 — Adaptador WA como microservicio ← estamos aquí
- `index.js` se convierte en un adaptador puro: escucha mensajes, los retransmite al backend Python
- El backend Python toma todas las decisiones de negocio

### Etapa 3 — Features de IA y browser
- Playwright integrado en el backend Python
- LangGraph para flujos de agente (Feature #6 del modelo de features)
- El agente puede usar el browser como herramienta

### Etapa 4 — Producción
- Migrar de SQLite a PostgreSQL
- Despliegue separado de cada componente
- Reemplazar WhatsApp Web por API oficial (cuando tenga sentido económico)

---

## Decisiones pendientes

| Decisión | Opciones | Estado |
|----------|----------|--------|
| ¿Cuándo empezar la migración a Python? | — | ✅ Ya migrado |
| ¿Frontend: refactor del actual o nuevo? | — | ✅ Reescritura limpia en React |
| ¿SQLite → PostgreSQL en qué etapa? | Desde el inicio en Python / más adelante | 🟡 SQLite por ahora, migrar en Etapa 4 |
| ¿Adaptador WA: mantener Node.js o buscar alternativa? | Node.js transitorio / API oficial | 🟡 Transitorio — Etapa 2 pendiente |

---

## Lo que NO cambia

- El modelo de entidades: empresa, clientes, puntos de entrada, features progresivos
- El modelo de negocio
- La UX del panel admin (cambia la implementación, no el diseño)
- El hecho de que la tecnología es invisible para el usuario final

---

*Documento vivo. Refleja la dirección de largo plazo, no compromisos inmediatos.*
