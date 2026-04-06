# Plan de tareas para subagentes

Cada tarea es atómica y ejecutable por un agente sin contexto previo.
Incluye: qué hacer, archivos exactos, cómo verificar.

---

## TAREA 1 — Limpiar node_types.py: sacar tipos obsoletos

**Contexto:** `backend/graphs/node_types.py` es el catálogo que expone el endpoint
`GET /api/flow/node-types`. Hoy incluye tipos que ya no existen en el registry ni en la paleta.
El endpoint devuelve basura que confunde al frontend.

**Qué hacer:** en `backend/graphs/node_types.py`, eliminar las siguientes entradas del dict `NODE_TYPES`:
- `"start"` — era de LangGraph, no existe más
- `"end"` — ídem
- `"search"` — eliminado (reemplazado por vector_search)
- `"notify"` — eliminado (reemplazado por send_message)
- `"reply"` — el tipo se llama `send_message` ahora (reply.py es el nombre del archivo, no del tipo)
- `"generic"` — es un fallback interno, no un tipo público
- `"luganense_flow"` — mega-nodo eliminado

También eliminar de `classify()` (función al final del archivo) cualquier referencia a `"notify"` y `"search"` — ya están removidas pero verificar.

**Verificar:**
```bash
curl -s http://localhost:8000/api/flow/node-types | python3 -c "
import sys, json
[print(t['id']) for t in json.load(sys.stdin)]
"
```
Debe mostrar solo: `router`, `fetch`, `vector_search`, `send_message`, `llm`, `reply` (si existe), `summarize`, `llm_respond`, `message_trigger`.

**Commit:** `refactor(node_types): eliminar tipos obsoletos del catálogo público`

---

## TAREA 2 — Eliminar alias llm_respond del registry

**Contexto:** `backend/graphs/nodes/__init__.py` tiene `"llm_respond": LLMNode` como alias legacy.
Ya no hay flows que usen `llm_respond` — fue migrado a `llm`. Mantenerlo genera ruido en el catálogo.

**Verificar antes de tocar:**
```bash
backend/.venv/bin/python -c "
import sqlite3, json
conn = sqlite3.connect('data/messages.db')
for name, defn in conn.execute('SELECT name, definition FROM flows').fetchall():
    types = [n['type'] for n in json.loads(defn).get('nodes', [])]
    if 'llm_respond' in types:
        print(f'USAR: {name} — {types}')
conn.close()
print('scan done')
"
```
Si el scan no muestra ningún flow usando `llm_respond`, proceder.

**Qué hacer:**
- En `backend/graphs/nodes/__init__.py`: eliminar la línea `"llm_respond": LLMNode,` del dict `NODE_REGISTRY`
- En `backend/graphs/node_types.py`: eliminar la entrada `"llm_respond"` de `NODE_TYPES`

**Commit:** `refactor(nodes): eliminar alias llm_respond del registry`

---

## TAREA 3 — Agregar una colección nueva a COLLECTION_REGISTRY

**Contexto:** `VectorSearchNode` busca en colecciones registradas en `backend/graphs/collections.py`.
Hoy están `luganense_oficios` y `luganense_auspiciantes`.

**Cómo agregar una colección nueva (template):**

1. Crear el handler en `backend/graphs/collections.py`:
```python
async def _search_mi_coleccion(query: str, top_k: int, empresa_id: str) -> dict:
    # Lógica de búsqueda — puede ser vector, SQL, hardcodeado, etc.
    # Retorna dict con las keys que quieras en state.vars
    return {
        "nombre": "...",
        "telefono": "...",
        "text": "Texto principal para state.context",
    }
```

2. Registrar en `COLLECTION_REGISTRY`:
```python
COLLECTION_REGISTRY["mi_coleccion"] = _search_mi_coleccion
```

3. En el flow, crear un nodo `vector_search` con `config.collection = "mi_coleccion"`.
Los keys del dict retornado quedan disponibles como `{{nombre}}`, `{{telefono}}` en nodos siguientes.

**Verificar:** el test `backend/tests/test_vector_search.py` tiene `test_vector_search_registrados` que lista las colecciones. Agregar la nueva ahí y correr:
```bash
backend/.venv/bin/python -m pytest backend/tests/test_vector_search.py -v
```

---

## TAREA 4 — Agregar un nodo nuevo al framework

**Pasos exactos para agregar cualquier nodo:**

1. **Crear** `backend/graphs/nodes/mi_nodo.py`:
```python
from .base import BaseNode
from .state import FlowState

class MiNodoNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        # lógica
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "campo_string": {
                "type": "string",
                "label": "Label visible en UI",
                "default": "",
                "hint": "Explicación breve",
            },
            "campo_select": {
                "type": "select",
                "label": "Opciones",
                "default": "opcion_a",
                "options": ["opcion_a", "opcion_b"],
            },
            # show_if: {"otro_campo": "valor"} → campo condicional
        }
```

2. **Registrar** en `backend/graphs/nodes/__init__.py`:
```python
from .mi_nodo import MiNodoNode
# En NODE_REGISTRY:
"mi_nodo": MiNodoNode,
```

3. **Agregar al catálogo** en `backend/graphs/node_types.py`:
```python
"mi_nodo": NodeType(
    id="mi_nodo",
    label="Mi nodo",
    color="#hexcolor",
    description="Qué hace este nodo.",
),
```

4. **Agregar a la paleta** en `frontend/src/store/flowStore.js`:
```js
export const PALETTE_TYPES = [
  // ... existentes ...
  'mi_nodo',
]
```

5. **Reiniciar el backend** → `./restart-backend.sh`

El panel de configuración aparece solo. No hay que tocar el frontend.

**Verificar:**
```bash
curl -s http://localhost:8000/api/flow/node-types | python3 -c "
import sys, json
data = json.load(sys.stdin)
nodo = next((t for t in data if t['id'] == 'mi_nodo'), None)
print(nodo)
"
```

---

## Tipos de campo disponibles en config_schema()

| type | Render | Params extra |
|------|--------|-------------|
| `string` | Input texto | `hint`, `required` |
| `textarea` | Textarea | `hint`, `rows` (default 4) |
| `select` | Dropdown | `options: ["a","b"]` o `[{"value":"a","label":"A"}]` |
| `float` | Input numérico | `default` |
| `bool` | Checkbox | `default` |
| `list` | Input CSV → array | `hint` |

Campo condicional: agregar `"show_if": {"campo": "valor"}` — se oculta si no se cumple.
