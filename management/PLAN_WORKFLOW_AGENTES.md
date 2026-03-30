# Plan: Workflow Engine para Agentes de IA

**Creado:** 2026-03-29
**Reemplaza:** PLAN_LUGANENSE.md, PLAN_IA_AGENTES.md
**Alcance:** toda la plataforma Pulpo — no solo Luganense

---

## La visión

Pulpo se convierte en una plataforma para construir y operar **agentes de IA conversacionales**.

**Cada empresa tiene exactamente un flow.** El flow define toda la lógica de respuesta del bot — rutas, condiciones, nodos. No hay lista de herramientas: hay un grafo. La complejidad vive dentro del grafo, no en una lista de tools apiladas.

En la UI, la pestaña "Herramientas" desaparece. La reemplaza la pestaña **"Flow"** — que muestra el grafo del agente de esa empresa.

**Esto no es solo Luganense.** Luganense fue el primer proyecto que nos obligó a formalizar esta arquitectura. El modelo aplica a todas las empresas:

| Empresa | Flow |
|---------|------|
| Luganense | Scope Router → (Noticias: FetchFB → LLM) / (Oficio: FindWorker → Notify) |
| La Piquiteria | 1 nodo: reply fijo |
| GM Herrería | 1 nodo: reply fijo (a crear) |
| Cualquier empresa futura | Compone nodos según su caso de uso |

Un flow de 1 nodo es el caso más simple. Un flow de N nodos con routers condicionales es Luganense. El modelo escala.

---

## Arquitectura: Nodes + Flows

### Nodes — bloques atómicos reutilizables

Cada node hace **una sola cosa**. No sabe quién lo llama ni qué viene después.

| Node | Descripción | Implementado |
|------|-------------|:---:|
| `reply` | Devuelve texto fijo | ✅ (fixed_message) |
| `llm_respond` | LLM con contexto dado | ✅ (assistant/luganense) |
| `llm_classify` | Clasifica intención (router) | ✅ (scope_router) |
| `fetch_facebook` | Scraping headless FB | ✅ |
| `find_worker` | Busca trabajador por oficio | ✅ |
| `notify_worker` | Notifica trabajador TG/WA | ✅ |
| `search_sponsors` | Elige auspiciante random | ✅ |
| `summarize` | Acumula mensajes en texto | ✅ (summarizer) |
| `fetch_instagram` | Posts de Instagram | ❌ futuro |
| `fetch_wa_history` | Historial WA de un contacto | ❌ futuro |
| `search_db` | Busca en tablas de la DB | ❌ futuro |
| `handoff_human` | Escala a operador humano | ❌ futuro |

### Flows — grafos LangGraph

Un flow es un grafo LangGraph que conecta nodes.

```
# Luganense (implementado)
[scope_router] ──noticias──> [fetch_facebook] → [llm_respond] → [search_sponsors] → END
               └──oficio───> [find_worker] → [notify_worker] → END

# La Piquiteria (a migrar)
[reply("Hola, somos La Piquiteria...")] → END

# Summarizer (a migrar)
[summarize] → END   ← (no envía respuesta al usuario)

# Ejemplo futuro
[llm_classify] → [fetch_instagram] → [fetch_facebook] → [llm_respond] → END
```

**Principio clave:** todo es un flow. Un mensaje fijo es un flow de 1 nodo `reply`. Un assistant es un flow de 1 nodo `llm_respond`. No hay distinción de tipos — solo flows con distinta cantidad de nodos.

---

## Estado actual (2026-03-29)

### Implementado en código
- `backend/graphs/luganense.py` — grafo LangGraph completo, funciona en producción
- `backend/nodes/fetch_facebook.py` — scraping headless con Playwright
- `backend/nodes/find_worker.py`, `notify_worker.py` — oficios
- `backend/graphs/auspiciantes.py` — selección de auspiciantes

### Implementado en UI
- Campo `tipo: "flow"` visible en lista de herramientas de la empresa
- Modal "Editar herramienta" tiene opción "Flow (grafo)" en el selector de tipo
- Sin visualización del grafo (solo nombre + tipo)

### Pendiente de migrar
- `fixed_message` y `summarizer` aún son tipos ad-hoc, no representados como flows con nodos
- El modal "Editar herramienta" no muestra el grafo del flow

---

## Fase 1 — Vista del grafo en "Editar herramienta" (próxima)

**Objetivo:** reemplazar la pestaña "Herramientas" de cada empresa por una pestaña **"Flow"** que muestra el grafo del agente como nodos y flechas.

**Solo lectura en esta fase. No hay edición todavía.**

### Cambio de modelo en la UI

| Antes | Después |
|-------|---------|
| Tab "Herramientas" con lista de tools | Tab "Flow" con canvas del grafo |
| Cada tool tiene nombre, tipo, toggle on/off | Un solo flow, siempre activo |
| "Editar herramienta" abre un form genérico | "Ver flow" abre el canvas con los nodos |
| Empresas pueden tener 0, 1 o N tools | Cada empresa tiene exactamente 1 flow |

### Lo que se ve en la tab "Flow"

```
┌──────────────────────────────────────────────┐
│  Agente Luganense                             │
│                                               │
│  ▶ START                                      │
│     │                                         │
│  ⑂ scope_router                               │
│     │ noticias              │ oficio           │
│  ⬇ fetch_facebook      ⬇ find_worker         │
│     │                       │                 │
│  🤖 llm_respond         🔔 notify_worker      │
│     │                       │                 │
│  🔔 search_sponsors      ■ END                │
│     │                                         │
│  ■ END                                        │
└──────────────────────────────────────────────┘
```

### Implementación

**Backend — endpoint del grafo:**
```
GET /api/empresas/{empresa_id}/flow/graph
→ {
    nodes: [{ id, label, type }],
    edges: [{ source, target, label? }]
  }
```

Extracción desde LangGraph:
```python
graph_data = app.get_graph()
nodes = [{"id": n, "label": n, "type": classify_node(n)} for n in graph_data.nodes]
edges = [{"source": e[0], "target": e[1], "label": e[2] if len(e) > 2 else None}
         for e in graph_data.edges]
```

Cada empresa tiene un `flow_id` en su config → mapea a un módulo en `backend/graphs/`.

**Frontend — nueva tab "Flow" en EmpresaCard:**
- Reemplaza la tab "Herramientas" (o convive durante la migración)
- Muestra `<FlowCanvas graph={graph} />` con React Flow
- Nodos coloreados por tipo:

| Tipo | Color | Ícono |
|------|-------|-------|
| `router` / `classify` | Amarillo | ⑂ |
| `fetch` | Azul | ⬇ |
| `llm` | Violeta | 🤖 |
| `reply` | Gris | 💬 |
| `notify` | Naranja | 🔔 |
| `summarize` | Verde | 📝 |
| `__start__` | Verde oscuro | ▶ |
| `__end__` | Rojo | ■ |

**Stack:** `@xyflow/react` (React Flow v12)

### Worktree sugerido
```
git worktree add /Users/josetabuyo/Development/pulpo/feat-flow-ui -b feat-flow-ui
```
Backend `:8001`, Frontend `:5174`

---

## Fase 2 — Migrar todos los tools actuales a flows

Una vez que la vista funciona, migrar los tipos existentes al modelo de flows.

### fixed_message → flow de 1 nodo

```python
# backend/graphs/fixed_message.py
from langgraph.graph import StateGraph, END

_builder = StateGraph(...)
_builder.add_node("reply", lambda state: {"reply": state["prompt"]})
_builder.set_entry_point("reply")
_builder.add_edge("reply", END)
app = _builder.compile()
```

El modal muestra: `[reply] → END`

### summarizer → flow de 1 nodo

```python
# backend/graphs/summarizer_flow.py
_builder.add_node("summarize", summarizer_node)
# summarize: acumula mensajes, no envía respuesta
```

El modal muestra: `[summarize] → END`

**Impacto:** el campo `tipo` en DB eventualmente tiene solo un valor: `"flow"`. Los tipos `fixed_message`, `summarizer`, `assistant` son flows predefinidos, no tipos especiales.

---

## Fase 3 — Editor online de flows (largo plazo)

Después de que la vista funciona y todos los tools son flows:

- Arrastrar nodos al canvas
- Conectar nodos con flechas
- Configurar cada nodo (prompt del LLM, texto del reply, etc.)
- Guardar → persiste la definición del grafo en DB
- "Simular mensaje" → ver la ejecución paso a paso en el canvas

**Este es el corazón del producto:** un no-code workflow builder para agentes conversacionales.

---

## Luganense — estado operativo

Primer workflow real en producción. Ver detalles operativos en `NEXT_SESSION.md` del worktree `feat-luganense`.

### Resumen técnico
- Scope Router → Noticias (fetch FB headless + Groq) / Oficio (find + notify worker)
- 5 posts scrapeados via seeds pfbid hardcodeados
- Groq `llama-3.3-70b-versatile` — pipeline directo (sin ReAct, no soporta tool calling en JSON)
- Monitor de cookies: cron 9am → alerta Telegram si expiran < 14 días
- Cookies actuales expiran principios de abril 2026

### Pendiente Luganense
- ADMIN_CHAT_ID configurado ✅ (6593910266)
- Renovar cookies antes de principios de abril
- Seeds hardcodeados en `fetch_facebook.py` → actualizar si Luganense cambia sus Destacados

---

## Hoja de ruta global

```
✅ Fase 0 — Luganense: primer workflow real en producción (2026-03-29)
              Scope Router + FetchFB + FindWorker + Notify + Auspiciantes

📋 Fase 1 — Vista del grafo en UI
              Modal "Editar herramienta" muestra el grafo del flow (solo lectura)
              Backend: GET /tools/{id}/graph
              Frontend: FlowCanvas con React Flow

📋 Fase 2 — Migrar todos los tools a flows
              fixed_message → flow([reply])
              summarizer → flow([summarize])
              assistant → flow([llm_respond])
              Un solo tipo: "flow"

📋 Fase 3 — Editor online de flows
              Drag & drop de nodos, configuración, simulación

📋 Fase 4 — Biblioteca de nodes expandida
              fetch_instagram, fetch_wa_history, search_db, handoff_human, etc.

📋 Fase 5 — RAG por empresa
              Cada empresa sube documentos → nodes pueden buscar en ellos

📋 Fase 6 — Marketplace de flows
              Templates de flows predefinidos que el cliente activa con un click
```

---

## Variables de entorno actuales (prod)

```env
GROQ_API_KEY=gsk_...          # LLM — Groq/Llama (gratis)
ADMIN_CHAT_ID=6593910266      # Alerts Telegram → José
FB_EMAIL=...                  # Login FB para cookies
FB_PASSWORD=...
```
