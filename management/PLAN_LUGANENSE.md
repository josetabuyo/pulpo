# Plan Luganense — Bot comunitario con LangGraph

**Creado:** 2026-03-28
**Estado:** En progreso — Paso 1 completado (Telegram conectado)
**Worktree:** `feat-luganense` (`:8001` / `:5174`)

---

## Quién es Luganense

**Luganense** es el portal comunitario del barrio **Villa Lugano**, Buenos Aires.

| Canal | Estado | Datos |
|-------|--------|-------|
| Facebook | ✅ Principal | 49.000+ seguidores, Página · Comunidad |
| Instagram | ✅ Activo | @luganense_ |
| YouTube | ✅ Activo | @luganense_cultura |
| Threads | ✅ Activo | @luganense_ (4.1K) |
| Telegram | 🚧 Nuevo | @luganense_bot (creado 2026-03-28) |

**Qué hace:** Publica noticias del barrio, apoya emprendedores y comercios locales, conecta a vecinos con servicios y oficios del barrio.

**Contacto:** luganenses@gmail.com

---

## Principio de diseño: Nodes + Flows

La arquitectura separa dos conceptos que nunca deben mezclarse:

### Nodes — bloques atómicos reutilizables
Cada node hace **una sola cosa**. No sabe quién lo llama ni qué viene después.

| Node | Qué hace |
|------|----------|
| `fetch_facebook` | Trae posts/info de la Graph API de Facebook |
| `fetch_instagram` | Trae posts/stories de Instagram |
| `fetch_wa_history` | Lee historial de mensajes de WA de un contacto |
| `search_db` | Busca en tablas de la DB (auspiciantes, oficios, contactos) |
| `llm_respond` | Genera una respuesta libre con un LLM dado un contexto |
| `llm_curate` | Reformula/limpia texto con un LLM |
| `llm_classify` | Clasifica la intención del mensaje (scope router) |
| `send_message` | Envía un mensaje al usuario por el canal original |
| `notify_user` | Notifica a un tercero (trabajador, admin) |
| `search_sponsors` | Busca auspiciante relevante en la lista |
| `search_workers` | Busca trabajador por oficio en la lista |

### Flows — grafos que conectan nodes
Un flow es un grafo LangGraph que encadena nodes en un orden determinado.

```
# Ejemplo: flow_luganense_noticias
fetch_facebook → llm_curate → search_sponsors → send_message

# Ejemplo: flow_luganense_oficio
llm_classify(oficio) → search_workers → notify_user(trabajador) → track_job

# Ejemplo: flow_simple (lo implementado hoy — assistant)
llm_respond(contexto_estático) → send_message

# Ejemplo futuro arbitrario:
fetch_facebook → fetch_instagram → fetch_wa_history → llm_respond → send_message
```

**El `assistant` de hoy** es el flow más simple posible: un solo node `llm_respond` con contexto estático cargado a mano. En el futuro ese contexto lo provee un node `fetch_facebook` real.

**El cliente edita flows, no nodes.** Los nodes son código. Los flows son configuración que el cliente arrastra en el editor visual.

---

## La visión del bot

La gente que sigue a Luganense en cualquier canal podrá hablar con un bot que:

1. **Responde preguntas sobre noticias o novedades** del foro Luganense (busca en el contenido de Facebook)
2. **Conecta vecinos con oficios y contratistas** del barrio (herreros, electricistas, plomeros, albañiles, arquitectos, etc.)

El bot no es un asistente genérico: es el asistente del barrio.

---

## Arquitectura del bot: LangGraph + Scope Router

```
MENSAJE ENTRANTE (Telegram / FB Messenger / WA / Instagram)
         │
         ▼
   ┌─────────────┐
   │ SCOPE ROUTER│  ← Llama al LLM para clasificar la intención
   └──────┬──────┘
          │
     ┌────┴────┐
     │         │
     ▼         ▼
 NOTICIAS   BUSCAR OFICIO
     │             │
     ▼             ▼
BUSCAR EN FB  IDENTIFICAR OFICIO
(Graph API o       │
 texto cargado)    ▼
     │       BUSCAR TRABAJADOR
     ▼       (en lista jerárquica)
CURAR CON LLM      │
(elaborar rta)     ▼
     │       NOTIFICAR TRABAJADOR
     ▼       (mensaje Telegram/WA)
BUSCAR             │
AUSPICIANTE        ▼
(mostrar msg  CONFIRMAR ACEPTACIÓN
del sponsor)       │
     │             ▼
     ▼       NOTIFICAR CLIENTE
RESPONDER    "Tu pedido fue aceptado"
                   │
                   ▼
             SEGUIMIENTO DE ESTADOS
             (aceptado → en camino → terminado)
                   │
                   ▼
             FEEDBACK (7 días después)
             "¿Cómo salió el trabajo? 1-5 ⭐"
```

---

## LLM: modelos gratuitos

Se abandona la dependencia de Anthropic para este proyecto. Opciones gratuitas verificadas (2026):

### Recomendado: Groq (Llama 4)

| Aspecto | Detalle |
|---------|---------|
| **Modelos** | Llama 4 Scout, Llama 3.3 70B, Mixtral |
| **Velocidad** | 300+ tokens/seg (LPU hardware) |
| **Tier gratis** | ~30 req/min, generoso |
| **API** | OpenAI-compatible (`base_url="https://api.groq.com/openai/v1"`) |
| **Ya en uso** | Sí — ya está en `requirements.txt` para transcripción de audio |
| **Key** | Variable `GROQ_API_KEY` (ya existe en entorno de producción) |

```python
# Integración con LangGraph — literalmente un cambio de base_url
from langchain_groq import ChatGroq

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))
```

### Alternativa: Gemini Flash (Google AI Studio)
- 1 millón de tokens de contexto
- Tier gratuito muy generoso
- Requiere `GOOGLE_API_KEY`

**Decisión:** Usar **Groq** como primario (ya integrado, key disponible). Groq como fallback también para transcripción de audio.

---

## Hoja de ruta — Pasos incrementales

### ✅ Paso 0 — Setup inicial (DONE)
- Empresa `luganense` creada en Pulpo
- Bot Telegram `@luganense_bot` conectado (`luganense-tg-8502732053`)
- Tipo de tool `assistant` habilitado en DB
- `anthropic` SDK instalado (puede reemplazarse por Groq)

### ✅ Paso 1 — Bot assistant simple con Groq (DONE 2026-03-28)
**Objetivo:** El bot responde preguntas sobre Luganense usando texto estático como contexto.

**Qué hacer:**
1. Reemplazar `anthropic` por `langchain-groq` en `tools/assistant.py`
2. Crear empresa Luganense en el portal admin
3. Crear tool tipo `assistant` con el contenido de la página de Facebook como prompt
4. Probar: "¿A qué hora abren?" → bot responde con info del contexto

**Resultado:** Bot funcional en Telegram respondiendo preguntas básicas sobre el barrio. Testeado con simulador — Groq/Llama respondiendo correctamente, incluyendo "no sé" cuando no tiene info.

---

### 📋 Paso 2 — Scope Router (primer grafo LangGraph)
**Objetivo:** El bot clasifica si la pregunta es sobre noticias o sobre un oficio.

**Qué implementar:**
```python
# backend/graphs/luganense_graph.py

from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

class State(TypedDict):
    message: str
    scope: Literal["noticias", "oficio", "otro"]
    response: str

def scope_router(state: State) -> State:
    """Clasifica la intención del mensaje."""
    prompt = f"""
Clasificá este mensaje de un vecino de Villa Lugano en UNA sola categoría:
- "noticias": pregunta sobre el barrio, novedades, eventos, noticias
- "oficio": busca un herrero, electricista, plomero, albañil, arquitecto u otro trabajador
- "otro": cualquier otra cosa

Mensaje: {state["message"]}
Responde SOLO la categoría, sin explicación.
"""
    result = llm.invoke(prompt)
    state["scope"] = result.content.strip().lower()
    return state

def route_by_scope(state: State) -> str:
    return state["scope"]

builder = StateGraph(State)
builder.add_node("scope_router", scope_router)
builder.add_node("handle_noticias", handle_noticias)
builder.add_node("handle_oficio", handle_oficio)
builder.add_node("handle_otro", handle_otro)

builder.set_entry_point("scope_router")
builder.add_conditional_edges("scope_router", route_by_scope, {
    "noticias": "handle_noticias",
    "oficio": "handle_oficio",
    "otro": "handle_otro",
})

graph = builder.compile()
```

**En Pulpo:** El tipo de tool `"graph"` ejecuta un grafo en lugar de devolver texto fijo.

---

### 📋 Paso 3 — Rama Noticias completa

**Nodo: handle_noticias**
1. Buscar en el contenido de Luganense (texto cargado o Graph API de FB)
2. Curar la respuesta con el LLM: "Elaborá una respuesta clara y amigable"
3. Buscar auspiciante relevante (de una lista en DB o JSON)
4. Agregar mensaje del auspiciante al final de la respuesta

**Data model para auspiciantes:**
```json
{
  "auspiciantes": [
    {
      "id": "optica_lugano",
      "nombre": "Óptica Lugano",
      "mensaje": "👁️ ¿Sabías que en Óptica Lugano tenés 20% off para vecinos del barrio?",
      "tags": ["salud", "familia", "general"]
    }
  ]
}
```

**Lógica de selección:** auspiciante random entre los activos (en el futuro: relevante por tags).

---

### 📋 Paso 4 — Rama Oficios completa

**Flujo detallado:**
1. **Identificar oficio**: LLM extrae el oficio específico ("herrero", "electricista", etc.)
2. **Buscar trabajador**: en lista jerárquica `oficios.json`
3. **Notificar trabajador**: enviarle mensaje por Telegram/WA
4. **Esperar respuesta**: el trabajador confirma o rechaza
5. **Notificar cliente**: "¡Encontramos a alguien! Te va a contactar Juan García"
6. **Seguimiento de estado**: botones inline de Telegram para actualizar estado
7. **Feedback a los 7 días**: cron job que envía "¿Cómo salió? ⭐"

**Data model para oficios:**
```json
{
  "oficios": {
    "herrero": [
      {
        "nombre": "Juan García",
        "telegram_id": "123456789",
        "whatsapp": "5491100000001",
        "zona": "Villa Lugano",
        "rating": 4.8,
        "activo": true
      }
    ],
    "electricista": [...],
    "plomero": [...],
    "albañil": [...],
    "arquitecto": [...]
  }
}
```

**Estado del trabajo en DB:**
```sql
CREATE TABLE jobs (
  id            INTEGER PRIMARY KEY,
  empresa_id    TEXT NOT NULL,  -- luganense
  cliente_phone TEXT NOT NULL,
  cliente_name  TEXT,
  canal         TEXT NOT NULL,  -- telegram/whatsapp/facebook
  oficio        TEXT NOT NULL,  -- herrero/electricista/etc
  trabajador_id TEXT,
  status        TEXT NOT NULL,  -- pending/accepted/in_progress/done/rated
  rating        INTEGER,
  created_at    DATETIME,
  updated_at    DATETIME
)
```

---

### 📋 Paso 5 — Integración Facebook Messenger (cuando Meta apruebe)
**Ver:** Análisis en la sesión de 2026-03-28.

Requiere:
- App Review de Meta (4-8 semanas)
- Webhook `GET/POST /api/facebook/webhook/{page_id}` en Pulpo
- Page Access Token del Luganense

---

### 📋 Paso 6 — Editor visual de grafos (para el cliente)

**Objetivo:** Que el cliente (dueño de Luganense) pueda editar el flujo del bot sin código.

**Qué es:** Un editor de nodos en el frontend de Pulpo, específico por empresa.

**Componentes:**
- Canvas con nodos arrastrables (React Flow o similar)
- Tipos de nodo disponibles: Texto fijo, LLM con prompt, Condición/Router, Buscar en lista, Notificar usuario
- Conexiones entre nodos → generan el grafo LangGraph en backend
- Persistencia en DB: `grafo_json` en tabla `tools`
- Preview: "Simular mensaje" → ver cómo lo procesa el grafo

**Esto es el corazón del producto a futuro:** un no-code workflow builder para bots conversacionales.

---

## Mejoras necesarias en Pulpo para soportar Luganense

| Mejora | Razón | Prioridad |
|--------|-------|-----------|
| `backend/nodes/` — librería de nodes atómicos | Base reutilizable para todos los flows | Alta |
| Tipo de tool `"flow"` | Ejecutar un grafo LangGraph completo | Alta |
| Campo `flow_definition` en tools | JSON que describe qué nodes conectar y cómo | Alta |
| `jobs` table | Seguimiento de trabajos de oficios | Media |
| `auspiciantes` config por empresa | Lista de auspiciantes en JSON o DB | Media |
| `oficios` config por empresa | Lista de trabajadores por oficio | Media |
| Editor visual de nodos (frontend) | El cliente arma flows arrastrando nodes | Baja (futuro) |
| `langgraph` + `langchain-groq` como deps | `pip install langgraph langchain-groq` | Alta |

**Nota:** el tipo `"assistant"` (hoy) es un caso particular de `"flow"` con un solo node. Cuando Pulpo soporte `"flow"` completo, `"assistant"` puede migrar o convivir como alias del flow más simple.

---

## Configuración inicial de Luganense en Pulpo

```bash
# Ya hecho:
POST /api/bots  →  { "id": "luganense", "name": "Luganense", "password": "luganense2024" }
POST /api/telegram  →  { "botId": "luganense", "token": "8502732053:..." }

# Próximo: crear tool Q&A con contenido de Facebook
POST /api/empresas/luganense/tools  →  {
  "nombre": "Asistente Luganense",
  "tipo": "assistant",
  "config": {
    "prompt": "<contenido de la página de Facebook: descripción, horarios, noticias recientes, etc.>"
  },
  "incluir_desconocidos": true,
  "exclusiva": true,
  "conexiones": ["luganense-tg-8502732053"]
}
```

---

## Stack técnico

| Componente | Tecnología |
|-----------|-----------|
| Backend | FastAPI + Python |
| LLM | Groq API (Llama 4 / Llama 3.3 70B) — gratuito |
| Orquestación | LangGraph |
| Canal primario hoy | Telegram |
| Canales futuros | Facebook Messenger, Instagram DM, WhatsApp |
| DB | SQLite (jobs, auspiciantes, oficios) |
| Frontend | React + Vite (editor de nodos futuro) |

---

## Orden de trabajo — Sesiones futuras

```
Sesión actual:   Paso 1 — Q&A simple con Groq + contexto Facebook
Siguiente sesión: Paso 2 — Scope Router con LangGraph
                  Paso 3 — Rama Noticias + Auspiciantes
Sesión posterior: Paso 4 — Rama Oficios + Seguimiento
Largo plazo:      Paso 5 — Facebook Messenger
                  Paso 6 — Editor visual de nodos
```

---

## Variables de entorno necesarias

```env
GROQ_API_KEY=gsk_...          # Obtener en console.groq.com (gratis)
# ANTHROPIC_API_KEY=...       # Ya no necesaria para Luganense
```
