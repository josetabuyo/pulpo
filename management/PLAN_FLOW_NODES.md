# Plan: Sistema de Nodos — Refactorización y Generalización

**Objetivo:** Hacer que el editor visual de flows sea la única fuente de verdad.
Lo que se conecta gráficamente, se ejecuta igual en el backend.
Nodos genéricos y configurables. Luganense es un caso particular, no una excepción.

---

## Principios de diseño

1. **Visual = Código.** Los edges del editor son el grafo de ejecución real. El engine sigue los edges, no secuencia lineal.
2. **Todo configurable.** Ningún nodo tiene lógica hardcodeada. La config del nodo en el JSON es suficiente para ejecutarlo.
3. **Input como punto de entrada explícito.** El nodo `input_text` reemplaza a `__start__` y contiene la config de filtrado (conexión, contacto). Así el flow se auto-documenta.
4. **Sin nodo fin.** `__end__` se elimina. El engine termina cuando no hay más nodos a ejecutar según los edges.
5. **Sin código Luganense-específico.** `LuganenseFlowNode` desaparece. El flow de luganense usa nodos genéricos con config específica.

---

## Catálogo de nodos final

### `input_text`
Reemplaza a `__start__`. Punto de entrada del flow.
```json
{
  "connection_id": "bot_test-tg-8672986634",
  "contact_phone": null
}
```
- `connection_id`: qué conexión alimenta este flow (WA phone o Telegram session)
- `contact_phone`: null = todos los contactos, o un número específico

> **Implicación:** `connection_id` en la tabla `flows` pasa a vivir en la config del nodo `input_text`. La DB deja de necesitar esa columna (migración en Fase 5).

---

### `llm`
Llama al LLM con el mensaje del usuario + un prompt configurable. Puede responder o generar texto intermedio para pasar al siguiente nodo.
```json
{
  "prompt": "Respondé en nombre del barrio de Villa Lugano...",
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.7,
  "output": "reply"
}
```
- `output`: `"reply"` (responde al usuario) o `"context"` (guarda en `state.context` para el siguiente nodo)

---

### `query_expander`
Nodo especializado que toma el mensaje del usuario y genera una query optimizada para búsqueda. Es un `llm` con prompt fijo pero sobreescribible.
```json
{
  "prompt": "Convertí el mensaje en una query de búsqueda concisa y efectiva.",
  "output": "query"
}
```
- Guarda el resultado en `state.query` para que un `search` o `fetch` lo use.

---

### `router`
LLM decide qué rama ejecutar. Setea `state.route` con el key de la rama ganadora. El engine sigue solo los edges que parten del nodo con `label == state.route`.
```json
{
  "prompt": "Clasificá la consulta del usuario. Respondé con exactamente una palabra: 'noticias', 'oficio', o 'auspiciante'.",
  "routes": ["noticias", "oficio", "auspiciante"],
  "fallback": "noticias"
}
```

---

### `fetch`
HTTP GET/POST genérico. Guarda la respuesta en `state.context`.
```json
{
  "label": "Luganense - Facebook Posts",
  "url": "https://mbasic.facebook.com/groups/villalugano",
  "method": "GET",
  "headers": {},
  "extract": "text"
}
```
- `extract`: `"text"` (texto plano), `"json"`, `"html"`

---

### `search`
Busca en un portal externo usando `state.query` como término. Guarda resultados en `state.context`.
```json
{
  "label": "Luganense - Búsqueda de Oficios",
  "url": "https://mbasic.facebook.com/groups/luganense",
  "query_source": "state.query",
  "max_results": 5
}
```

---

### `notify`
Manda una notificación a un canal externo (Telegram, etc.).
```json
{
  "channel": "telegram",
  "recipient": "{{ADMIN_CHAT_ID}}",
  "template": "Nuevo pedido de oficio: {{state.message}} — de {{state.contact_name}}"
}
```
- Soporta variables `{{state.*}}` y `{{ENV_VAR}}`.

---

### `reply`
Respuesta fija de texto. Ya existe, sin cambios.
```json
{ "message": "Hola! Gracias por escribirnos..." }
```

---

### `summarize`
Acumula el contexto de la conversación. Ya existe, sin cambios.
```json
{}
```

---

## Fases de implementación

---

### Fase 0 — Limpieza y base (prerequisito)
**Alcance:** eliminar `__end__`, upgradar `BaseNode`, definir schemas de config.

**Tareas:**
- Eliminar `__end__` del `NODE_REGISTRY` y del engine (el engine termina cuando no hay edges salientes)
- Agregar a `BaseNode` un método `config_schema() -> dict` que describe los campos esperados (usado por el editor para renderizar el panel de config)
- Documentar en `NODE_TYPES` (frontend) cuáles campos tiene cada nodo y de qué tipo son (string, url, select, etc.)
- Eliminar `LuganenseFlowNode` del registry (todavía no del disco — se borra en Fase 4)

**Tests esperados:**
- `test_engine_sin_end_node`: flow sin `__end__` se ejecuta hasta el final sin error
- `test_base_node_config_schema`: cada nodo implementado devuelve un `config_schema` válido
- `test_node_types_frontend_sync`: los tipos del frontend coinciden con el `NODE_REGISTRY` del backend

---

### Fase 1 — Nodo `input_text` + engine sigue edges
**Alcance:** el nodo de entrada lleva la config de conexión. El engine ejecuta en orden topológico siguiendo los edges, no secuencialmente.

**Tareas:**
- Implementar `InputTextNode`: lee `connection_id` y `contact_phone` de su config. El engine usa esto para filtrar si el flow aplica al mensaje entrante (reemplaza el check en `get_active_flows_for_bot`).
- Refactorizar `execute_flow()` en `compiler.py`: en lugar de iterar `nodes` en orden de lista, construir un grafo con los edges y recorrerlo en orden topológico (BFS desde `input_text`).
- El engine respeta los labels de edges para el routing (Fase 2 los usa).

**Tests esperados:**
- `test_engine_sigue_edges_simple`: flow A→B→C se ejecuta en ese orden aunque estén desordenados en `nodes[]`
- `test_engine_input_text_filtra_conexion`: flow con `input_text.connection_id = "X"` no ejecuta si el mensaje viene de "Y"
- `test_engine_input_text_todos_contactos`: `contact_phone: null` en input_text ejecuta para cualquier contacto
- `test_engine_input_text_contacto_especifico`: `contact_phone: "123"` solo ejecuta para ese contacto

---

### Fase 2 — Router con branches
**Alcance:** `router` node + engine ejecuta solo el branch correcto.

**Tareas:**
- Implementar `RouterNode`: llama al LLM con el prompt, parsea la respuesta contra `routes[]`, setea `state.route`.
- Engine: cuando un nodo tiene múltiples edges salientes con `label`, solo sigue los que matchean `state.route`. Si no hay label en los edges, los sigue todos (comportamiento default actual).
- `fallback` en config de router: si el LLM no devuelve un route válido, usar el fallback.

**Tests esperados:**
- `test_router_clasifica_correctamente`: mensaje "quiero un plomero" → route = "oficio"
- `test_router_fallback_en_respuesta_invalida`: LLM devuelve texto inválido → usa fallback
- `test_engine_ejecuta_solo_branch_correcto`: router con route="oficio" → solo ejecuta nodos del branch "oficio", no los de "noticias"
- `test_engine_sin_label_ejecuta_todos`: edges sin label → todos los nodos sucesores se ejecutan

---

### Fase 3 — Nodos `llm`, `query_expander`, `fetch`, `search`, `notify`
**Alcance:** implementar todos los nodos genéricos.

**Tareas por nodo:**

**`llm`:**
- Llama a Groq con `state.message` + `prompt` de config
- Si `output == "reply"` → `state.reply`
- Si `output == "context"` → `state.context` (string acumulable)
- Tests: responde con el prompt dado; no sobreescribe reply si ya hay uno (a menos que sea explícito)

**`query_expander`:**
- LLM con prompt de expansión de queries
- Guarda en `state.query`
- Test: expande "quiero un herrero" a una query más rica

**`fetch`:**
- `httpx.get(url)` o POST
- Extrae texto/json/html según config
- Guarda en `state.context`
- Tests: fetch a URL real devuelve contenido; fetch con error HTTP maneja gracefully

**`search`:**
- Usa `state.query` (o `state.message` si no hay query) para buscar en el portal
- Parsea resultados básicos (texto relevante)
- Guarda en `state.context`
- Tests: search con query válida devuelve resultados; search con portal caído no rompe el flow

**`notify`:**
- Renderiza template con `state.*` y env vars
- Envía a Telegram (canal default) u otro canal configurable
- Tests: notificación se envía con los datos correctos; variables del template se reemplazan

**Tests de integración Fase 3:**
- `test_flow_llm_to_reply`: flow input_text → llm(output=reply) produce respuesta
- `test_flow_query_expander_to_search`: flow input_text → query_expander → search produce context
- `test_flow_completo_luganense_generico`: flow que simula luganense con nodos genéricos responde correctamente a "necesito un herrero"

---

### Fase 4 — Migración de Luganense
**Alcance:** el flow visual de luganense usa nodos genéricos. `LuganenseFlowNode` queda deprecado.

**Tareas:**
- Configurar en el editor (o DB directamente) el flow de luganense con nodos genéricos:
  - `input_text` con config de conexión Telegram
  - `scope_router` → tipo `router`, prompt de clasificación de luganense
  - `expandir_consulta` → tipo `query_expander`
  - `buscar_posts_fb` → tipo `fetch`, URL del grupo Facebook de luganense
  - `responder_noticias` → tipo `llm`, prompt para responder sobre noticias del barrio
  - `obtener_imagen` → tipo `fetch`, URL de imagen
  - `buscar_oficio` → tipo `search`, label "Luganense - Oficios"
  - `notificar_oficio` → tipo `notify`, Telegram al admin
  - `buscar_auspiciante` → tipo `search`, label "Luganense - Auspiciantes"
  - `responder_auspiciante` → tipo `llm`, prompt para responder sobre auspiciantes
- Eliminar `LuganenseFlowNode` del disco y del registry
- Eliminar `graphs/luganense.py` (el LangGraph hardcodeado)

**Tests esperados:**
- `test_luganense_flow_generico_herrero`: "necesito un herrero" → notifica al admin y responde
- `test_luganense_flow_generico_noticias`: "qué pasó en el barrio?" → responde con info de Facebook
- `test_luganense_flow_generico_auspiciante`: "busco pizzería" → responde con auspiciante

---

### Fase 5 — DB: `connection_id` en el nodo, no en la tabla
**Alcance:** el filtrado de conexión pasa a vivir en el nodo `input_text`, la columna `connection_id` en `flows` queda como referencia de UI solamente (o se elimina).

**Tareas:**
- `get_active_flows_for_bot`: ya no filtra por `connection_id` en SQL — devuelve todos los flows activos de la empresa. El engine lee el nodo `input_text` para ver si aplica.
- Migración DB: columna `connection_id` pasa a ser `display_connection_id` (solo informativa para el editor) o se elimina.
- El editor de flows actualiza `input_text.config.connection_id` cuando el usuario cambia la conexión en el header del flow.
- `DISABLE_AUTO_REPLY_PHONES` sigue funcionando en el engine (check sobre `input_text.config.connection_id`).

**Tests esperados:**
- `test_flow_no_ejecuta_si_input_text_no_matchea`: flow con input_text.connection_id="X" no responde a mensajes de "Y"
- `test_disable_auto_reply_phones_con_input_text`: número en DISABLE_AUTO_REPLY_PHONES no responde aunque input_text lo incluya
- `test_migracion_flows_existentes`: flows creados antes de Fase 5 siguen funcionando

---

## Estado actual vs. target

| Aspecto | Hoy | Después |
|---|---|---|
| Filtrado de conexión | columna `connection_id` en DB + SQL | nodo `input_text` en el flow |
| Ejecución | secuencial (orden del array `nodes[]`) | topológica (siguiendo edges) |
| Routing | no implementado | `router` node + edge labels |
| Luganense | `LuganenseFlowNode` → LangGraph hardcodeado | nodos genéricos configurados |
| `__start__` / `__end__` | marcadores sin config | `input_text` configurable / eliminado |
| Config por nodo | solo `reply` tiene config real | todos los nodos tienen schema de config |

---

## Worktree sugerido

```
/Users/josetabuyo/Development/pulpo/feat-flow-nodes
BACKEND_PORT=8001
FRONTEND_PORT=5174
```

Empezar por **Fase 0** y **Fase 1** en conjunto — son las más fundamentales y desbloquean todo lo demás.
