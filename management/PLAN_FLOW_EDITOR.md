# Plan: Flow Editor — Editor visual de agentes conversacionales

**Creado:** 2026-04-03
**Worktree activo:** `feat-flow-ui`
**Alcance:** reemplazar la pestaña "Herramientas" con un editor visual completo de workflows

---

## Visión

Pulpo se convierte en una plataforma no-code para construir agentes de IA conversacionales.
El operador arrastra nodos al canvas, los conecta, los configura con doble clic, y el agente vive.

**La pestaña "Herramientas" desaparece.** La reemplaza **"Flows"** — un canvas donde se compone
el comportamiento completo del bot. Un flow de 1 nodo es un reply fijo. Un flow de N nodos
con routers condicionales es Luganense. El modelo escala.

**Modelo de negocio:** el admin habilita/deshabilita tipos de nodo por empresa.
Los clientes pagan por los nodos que usan.

---

## Modelo de datos: Conexiones, Contactos, Flows

### Pestañas del componente empresa (nombres definitivos)

```
Conexiones | Contactos | Flows
```

La pestaña "Herramientas" no existe más en ningún lugar del código.

### Routing de flows: quién activa qué

Un flow puede tener tres modos de activación:

| `connection_id` | `contact_phone` | Activa cuando... |
|-----------------|-----------------|------------------|
| `null`          | `null`          | Cualquier conexión + cualquier contacto |
| `"wa_123"`      | `null`          | Solo esa conexión, cualquier contacto |
| `"wa_123"`      | `"5491155..."` | Solo esa conexión + ese contacto específico |

El sistema evalúa los flows en orden de especificidad (más específico primero):
connection + contact → solo connection → sin filtro.

**El summarizer es especial:** requiere al menos un `contact_phone` configurado.
El frontend lo valida antes de guardar.

---

## Nodos disponibles — catálogo y schemas de config

Todos los nodos heredan de la misma clase base. La config de cada uno es un dict JSON
guardado en DB. El panel de doble-clic renderiza el formulario según el schema del tipo.

### Base: `NodeDef` (Python)

```python
@dataclass
class NodeDef:
    id: str               # "llm_respond"
    label: str            # "Respuesta LLM"
    color: str            # "#7c3aed"
    category: str         # "LLM" | "Fetch" | "Control" | "Reply" | "Util"
    description: str      # tooltip en el canvas
    config_schema: dict   # JSON Schema del panel de config
    plan_required: str    # "free" | "pro" | "enterprise"
    implemented: bool     # False = visible en paleta pero deshabilitado
```

### Catálogo inicial

#### Control
| id | label | Plan | Config |
|----|-------|------|--------|
| `scope_router` | Router de intención | free | `{ "routes": ["noticias", "oficio", "auspiciante"] }` |
| `condition` | Condición simple | pro | `{ "field": "last_message", "operator": "contains", "value": "hola" }` |

#### Reply
| id | label | Plan | Config |
|----|-------|------|--------|
| `reply` | Respuesta fija | free | `{ "text": "Hola, somos La Piquitería..." }` |
| `llm_respond` | Respuesta LLM | free | `{ "system_prompt": "...", "model": "llama-3.3-70b-versatile" }` |

#### Fetch
| id | label | Plan | Config |
|----|-------|------|--------|
| `fetch_facebook` | Posts de Facebook | pro | `{ "page_url": "https://facebook.com/luganense.fc", "max_posts": 5, "seeds": [] }` |
| `fetch_instagram` | Posts de Instagram | pro | (futuro) |

#### Búsqueda
| id | label | Plan | Config |
|----|-------|------|--------|
| `find_worker` | Buscar oficio | free | `{ "categories": ["plomero", "electricista"] }` |
| `search_sponsors` | Buscar auspiciante | free | `{ "max_sponsors": 3 }` |

#### Notificación
| id | label | Plan | Config |
|----|-------|------|--------|
| `notify_worker` | Notificar oficio | free | `{ "channel": "telegram", "template": "Nuevo pedido: {oficio}" }` |

#### Util
| id | label | Plan | Config |
|----|-------|------|--------|
| `summarize` | Sumarizador | pro | `{ "period_days": 30, "include_audio": true }` |
| `expand_query` | Expandir consulta | free | `{ "context_window": 3 }` |

---

## Esquema de DB

### Tabla `flows` (nueva)

```sql
CREATE TABLE flows (
  id            TEXT PRIMARY KEY,    -- UUID generado
  empresa_id    TEXT NOT NULL,
  name          TEXT NOT NULL,
  definition    TEXT NOT NULL,       -- JSON serializado: { nodes, edges, viewport }
  connection_id TEXT DEFAULT NULL,   -- NULL = todas las conexiones
  contact_phone TEXT DEFAULT NULL,   -- NULL = todos los contactos
  active        BOOLEAN DEFAULT TRUE,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla `node_permissions` (nueva — billing)

```sql
CREATE TABLE node_permissions (
  empresa_id TEXT NOT NULL,
  node_type  TEXT NOT NULL,
  enabled    BOOLEAN DEFAULT TRUE,
  PRIMARY KEY (empresa_id, node_type)
);
```

### Eliminar de DB
- Tabla `tools` → migrar datos a `flows` antes de borrar
- Campo `tool_tipo` en phones.json → reemplazado por `flow_id` en flows table
- Campo `tipo` (fixed_message/summarizer/assistant) → desaparece; todo es flow

### Estructura del JSON `definition`

```json
{
  "nodes": [
    {
      "id": "node_1a2b",
      "type": "scope_router",
      "position": { "x": 300, "y": 100 },
      "config": { "routes": ["noticias", "oficio"] }
    },
    {
      "id": "node_3c4d",
      "type": "fetch_facebook",
      "position": { "x": 150, "y": 250 },
      "config": {
        "page_url": "https://facebook.com/luganense.fc",
        "max_posts": 5,
        "seeds": ["pfbid02T..."]
      }
    }
  ],
  "edges": [
    { "id": "e1", "source": "node_1a2b", "target": "node_3c4d", "label": "noticias" }
  ],
  "viewport": { "x": 0, "y": 0, "zoom": 1 }
}
```

---

## Arquitectura frontend

### Stack

```
@xyflow/react   → canvas + nodos + edges
zustand         → estado global (nodes, edges, selectedNodeId, isDirty)
tailwindcss     → UI del panel de config
```

### Componentes

```
EmpresaCard.jsx
  └── Tab "Flows"
        ├── FlowList.jsx          → lista de flows de la empresa (con filtros por conexión/contacto)
        └── FlowEditor.jsx        → el editor visual
              ├── NodePalette.jsx  → sidebar izquierdo con tipos de nodo arrastrables
              ├── FlowCanvas.jsx   → canvas React Flow (actualizar el existente)
              │    └── FlowNode.jsx → nodo custom con doble-click → abre panel
              ├── NodeConfigPanel.jsx → panel lateral derecho con formulario de config
              └── FlowHeader.jsx   → nombre del flow, conexión/contacto, botón Guardar
```

### Estado con Zustand

```js
// store/flowStore.js
{
  nodes: [],
  edges: [],
  selectedNodeId: null,
  isDirty: false,
  setSelectedNodeId: (id) => ...,
  updateNodeConfig: (nodeId, config) => ...,
  onNodesChange: (changes) => ...,
  onEdgesChange: (changes) => ...,
  onConnect: (connection) => ...,
}
```

### Drag & drop de la paleta al canvas

```
1. NodePalette: onDragStart → e.dataTransfer.setData('nodeType', 'reply')
2. FlowCanvas: onDrop → const pos = screenToFlowPosition({ x, y })
              → crear nodo con id=uuid(), type, position, config=defaultConfig
3. onDragOver: e.preventDefault() para habilitar el drop
```

### Panel de config (doble-clic en nodo)

```
onNodeDoubleClick → setSelectedNodeId(node.id)
NodeConfigPanel renderiza según node.type:
  - reply: <textarea> para editar el texto
  - fetch_facebook: campos para page_url, seeds, max_posts
  - scope_router: input para cada ruta (agregar/quitar)
  - etc.
```

---

## Compilación a LangGraph en runtime

Al ejecutar un flow guardado en DB, el backend lo compila:

```python
# backend/graphs/compiler.py

NODE_REGISTRY = {
    "reply":         ReplyNode,
    "llm_respond":   LLMRespondNode,
    "scope_router":  ScopeRouterNode,
    "fetch_facebook": FetchFacebookNode,
    "find_worker":   FindWorkerNode,
    "notify_worker": NotifyWorkerNode,
    "search_sponsors": SearchSponsorsNode,
    "summarize":     SummarizeNode,
    "expand_query":  ExpandQueryNode,
}

def compile_graph(definition: dict) -> CompiledGraph:
    builder = StateGraph(AgentState)
    for node_def in definition["nodes"]:
        node_fn = NODE_REGISTRY[node_def["type"]](node_def["config"])
        builder.add_node(node_def["id"], node_fn)
    for edge in definition["edges"]:
        if edge.get("label"):
            # conditional edge — router ya conoce sus rutas
            ...
        else:
            builder.add_edge(edge["source"], edge["target"])
    builder.set_entry_point(definition["nodes"][0]["id"])
    return builder.compile()
```

Cada clase de nodo tiene `__init__(self, config: dict)` y `__call__(self, state)`.
El constructor recibe la config del DB. El `__call__` es la función del nodo LangGraph.

---

## Endpoints API (nuevos)

```
GET  /api/empresas/{id}/flows               → lista de flows
POST /api/empresas/{id}/flows               → crear flow
GET  /api/empresas/{id}/flows/{flow_id}     → detalle + definition
PUT  /api/empresas/{id}/flows/{flow_id}     → guardar definition (topología + config)
DELETE /api/empresas/{id}/flows/{flow_id}   → eliminar flow

GET  /api/flow/node-types                   → catálogo (ya existe)
GET  /api/empresas/{id}/node-permissions    → nodos habilitados para esta empresa (admin)
PUT  /api/empresas/{id}/node-permissions    → habilitar/deshabilitar nodo (admin only)
```

---

## Migración desde "Herramientas"

### Regla: hacer backward-compatible durante la migración

1. Mantener la lógica de `tools` en el auto-reply hasta que todos los flows estén migrados
2. Al leer la intención de la empresa: primero buscar en `flows` (nuevo), fallback a `tools` (viejo)
3. Una vez que todas las empresas tienen flows, borrar la tabla `tools` y el router de fallback

### Migrations por empresa

| Empresa | Tool actual | Flow equivalente |
|---------|-------------|-----------------|
| La Piquitería | summarizer | flow([summarize]) con contact_phone requerido |
| GM Herrería | fixed_message | flow([reply]) con text hardcodeado |
| bot_test | fixed_message | flow([reply]) |
| Luganense | flow (LangGraph) | ya es flow, migrar de phones.json a DB |

---

## Hoja de ruta por fases

### ✅ Fase 0 — Vista read-only del grafo (COMPLETA)
- Tab "Flow" en EmpresaCard
- Grafo de Luganense desde LangGraph real
- Grafos sintéticos para fixed_message/summarizer/assistant
- Labels con nombre de nodo (no tipo genérico)

### ✅ Fase 1 — DB + API de flows + Arquitectura de nodos (COMPLETA)

**Lo que se hizo:**
- Tabla `flows` en DB con migration
- Endpoints CRUD: GET list, POST, GET detail, PUT, DELETE
- `seed_default_flows()` crea flows iniciales desde phones.json al arrancar
- Arquitectura de nodos: `BaseNode`, `ReplyNode`, `LLMRespondNode`, `SummarizeNode`, `LuganenseFlowNode`
- `FlowState` dataclass — entrada/salida normalizada para todos los nodos
- `compiler.py` — `execute_flow()`, `resolve_flows()`, `run_flows()`
- WA, Telegram y simulador reescritos para usar `run_flows`
- Eliminado sistema "tools" completo (API, tabla DB, código, tests)
- `LOGIN_RATE_LIMIT=1000/hour` en `.env` de worktree para tests sin throttling
- Fix `delete_contact` para borrar channels explícitamente (aiosqlite no soporta event listeners)
- **106 tests pasando**

### 📋 Fase 2 — Editor drag & drop

**Scope:**
- NodePalette con tipos de nodo arrastrables
- FlowCanvas editable (nodesDraggable=true, nodesConnectable=true)
- Zustand store para estado del editor
- Botón "Guardar" → PUT /api/.../flows/{id}
- NodeConfigPanel con doble-clic (formularios por tipo de nodo)
- FlowHeader con nombre, selector de connection + contact
- Tests básicos del editor

**No incluye:** compilación a LangGraph aún.

### 📋 Fase 3 — Compilación + ejecución de flows desde DB

**Scope:**
- `backend/graphs/compiler.py` — NODE_REGISTRY + `compile_graph(definition)`
- Cada nodo Python tiene `__init__(config)` + `__call__(state)`
- Auto-reply lee flows de DB (con fallback a tools durante migración)
- Migrar todas las empresas existentes a flows
- Eliminar tabla `tools` y el fallback
- Eliminar campo `tipo` de la UI y del router backend
- Tests de integración: definición JSON → ejecución real

### 📋 Fase 4 — Billing / node permissions

**Scope:**
- Tabla `node_permissions` en DB
- Endpoint PUT /api/empresas/{id}/node-permissions (admin only)
- Frontend: nodos no habilitados aparecen en paleta con badge "Pro" y disabled
- Backend: al ejecutar flow, verificar que todos los nodos estén habilitados para la empresa

### 📋 Fase 5 — Portal empresa (cliente ve y edita su propio flow)

**Scope:**
- ConnectPage incluye el editor (sin paleta completa — solo ver + config de nodos existentes)
- El cliente puede editar la config de sus nodos (ej: cambiar texto de reply fijo)
- El admin puede habilitar/deshabilitar la edición por empresa

---

## Decisiones técnicas clave

| Decisión | Elegido | Motivo |
|----------|---------|--------|
| Persistencia de flows | Una columna JSON en DB | Igual que n8n, Flowise, Dify — flow es unidad atómica |
| State management | Zustand | React Flow lo usa internamente, cero overhead |
| Config panel | Formularios custom por tipo | Más control que RJSF para nuestro nivel de complejidad |
| Drag & drop paleta | HTML5 nativo + screenToFlowPosition | Patrón oficial React Flow |
| Compilación LangGraph | Runtime desde JSON | No hay soporte oficial para DSL declarativo |
| Auto-layout | dagre (ya instalado) | Suficiente para nuestro caso, elk solo si dagre no escala |
| Tab name | "Flows" (plural) | Puede haber múltiples flows por empresa |

---

## Lo que NO hacemos (para mantenerlo simple)

- No hay versionado de flows (v1, v2, etc.) — es YAGNI para ahora
- No hay simulación paso-a-paso en el canvas — es Fase 6+ si se necesita
- No hay export/import de flows entre empresas — luego si surge el caso
- No hay undo/redo en el editor — el botón "Guardar" es el checkpoint
- No hay grafos Python arbitrarios fuera del NODE_REGISTRY — todo nodo nuevo requiere implementación

---

## Estado del worktree feat-flow-ui

| Archivo | Estado |
|---------|--------|
| `backend/api/flows.py` | ✅ CRUD completo + seed_default_flows |
| `backend/graphs/node_types.py` | ✅ Fuente de verdad de tipos |
| `backend/graphs/nodes/` | ✅ BaseNode, ReplyNode, LLMRespondNode, SummarizeNode, LuganenseFlowNode |
| `backend/graphs/compiler.py` | ✅ execute_flow, resolve_flows, run_flows |
| `backend/sim.py` | ✅ Usa run_flows |
| `backend/bots/telegram_bot.py` | ✅ Usa run_flows |
| `backend/automation/whatsapp.py` | ✅ Usa run_flows |
| Tabla `flows` en DB | ✅ Con migration |
| Tabla `tools` y relacionadas | ✅ Eliminadas |
| `frontend/src/components/FlowCanvas.jsx` | ✅ Read-only, dagre layout |
| `frontend/src/components/EmpresaCard.jsx` | ✅ Tab "Flow" activa |
| `backend/tests/test_flows.py` | ✅ 106 tests totales pasando |
| Editor drag & drop (Fase 2) | ❌ pendiente |
| NodeConfigPanel (Fase 2) | ❌ pendiente |
| FlowList.jsx (Fase 2) | ❌ pendiente |
| Delta sync unificado (Fase 3) | ❌ pendiente |
