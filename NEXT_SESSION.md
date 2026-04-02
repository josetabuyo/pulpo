# NEXT_SESSION — Luganense: refactor grafo + imagen inteligente

<<<<<<< HEAD
## Contexto
Worktree: `bug-luganense` | Backend: `:8002` | `ENABLE_BOTS=false`
Arrancar: `./start.sh` desde la raíz de este worktree.
=======
## Estado actual
**Fase 1 COMPLETA y en producción** — tab "Flow" con grafo de agente, arquitectura SOLID.

Plan completo en: `management/PLAN_WORKFLOW_AGENTES.md`
>>>>>>> master

Doc de referencia: `management/BUG_LUGANENSE.md` (en master `_/`).

---

<<<<<<< HEAD
## Estado actual

- Todos los bugs originales resueltos
- MEJORA 1 (logs ricos) → en producción
- MEJORA 2 (imagen básica) → implementado, pendiente refactor antes de mergear
- feat-flow-ui → mergeado, el grafo descompuesto se verá en el visualizador
=======
## Arquitectura implementada

### Fuente de verdad: `backend/graphs/node_types.py`
`NodeType` dataclass con `id`, `label`, `color`, `description`.
Funciones `get(type_id)` y `classify(node_id)` usadas por todo el sistema.
**Agregar un tipo nuevo = editar solo este archivo.**

### Backend: `backend/api/flows.py`
- `GET /api/flow/node-types` — catálogo público (sin auth)
- `GET /api/empresas/{id}/flow/graph` — grafo de la empresa (auth requerida)
  - Empresas con `flow_id` en phones.json → grafo LangGraph real
  - Sin `flow_id` → busca herramienta activa en DB; si no hay, lee `tool_tipo` de phones.json

### Frontend: `frontend/src/components/FlowCanvas.jsx`
- Consume `/api/flow/node-types` para estilos y tooltips
- Nodo custom con tooltip nativo (`title`) al hacer hover
- Layout automático con dagre
- Importado en `EmpresaCard.jsx`, tab "Flow"

### phones.json (gitignoreado, editar en cada worktree y en `_`)
```json
{ "id": "gm_herreria",  "tool_tipo": "fixed_message" }
{ "id": "la_piquiteria","tool_tipo": "summarizer" }
{ "id": "bot_test",     "tool_tipo": "fixed_message" }
{ "id": "luganense",    "flow_id":   "luganense" }
```

### Tests: `backend/tests/test_flows.py` — 21 tests
- Unit: registro NodeType, classify(), get() fallback
- HTTP: `/api/flow/node-types` (estructura, sin auth, consistencia con registro)
- HTTP: `/api/empresas/{id}/flow/graph` (por empresa, tipos, edges)
>>>>>>> master

---

## Regla de esta sesión

<<<<<<< HEAD
Al terminar: **commit en bug-luganense → merge a master → push → restart backend de producción**.
=======
- Edición drag-drop: mover nodos, crear/eliminar edges desde la UI
- Eliminar la pestaña "Herramientas" cuando Flow la reemplace del todo
- Persistir topologías en DB
- Grafos Python reales para fixed_message/summarizer/assistant (hoy son sintéticos)
- Labels en edges condicionales (scope_router → "noticias" / "oficio")
- Agregar flow_id a nuevos grafos LangGraph cuando se creen
>>>>>>> master

---

## Tests antes de empezar

```bash
<<<<<<< HEAD
cd /Users/josetabuyo/Development/pulpo/bug-luganense/backend
/Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/test_fetch_facebook_logs.py tests/test_summarizer.py -v
=======
git merge feat-flow-ui
git push origin master
cd /Users/josetabuyo/Development/pulpo/_ && ./restart-backend.sh
>>>>>>> master
```
