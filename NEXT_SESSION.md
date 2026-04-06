# NEXT_SESSION — Estado actual del proyecto

## Contexto
Pulpo Flow = framework de nodos estilo n8n, local y propio.
Un nodo nuevo = crear clase Python con config_schema() + registrar. El frontend aparece solo.

## Estado al 2026-04-05 — todo en master, pusheado

### Nodos en producción
| Nodo | Archivo | Estado |
|------|---------|--------|
| `message_trigger` | nodes/message_trigger.py | ✅ |
| `router` | nodes/router.py | ✅ |
| `llm` | nodes/llm.py | ✅ |
| `send_message` | nodes/reply.py | ✅ |
| `vector_search` | nodes/vector_search.py | ✅ |
| `fetch` | nodes/fetch.py | ✅ genérico (fb_page_id) |
| `summarize` | nodes/summarize.py | ✅ |

### Arquitectura de schema
`config_schema()` en Python → `/api/flow/node-types` → `typeMap` en store → panel dinámico.
No hay NODE_SCHEMAS en el frontend. Agregar nodo = solo Python.

---

## Pendiente

### Limpieza del catálogo de tipos (node_types.py)
El endpoint devuelve tipos obsoletos: `search`, `notify`, `start`, `end`, `reply`, `generic`, `llm_respond`.
Ver `management/plan_subagentes.md` para tareas atómicas ejecutables.

### Test end-to-end Luganense
Pendiente por decisión del usuario. No urgente.

## Skip permissions
claude --dangerously-skip-permissions
