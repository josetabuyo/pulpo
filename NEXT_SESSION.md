# NEXT_SESSION — feat-flow-ui

## Estado actual
**Fase 1 COMPLETADA** — tab "Flow" de solo lectura funcional.

Plan completo en: `management/PLAN_WORKFLOW_AGENTES.md`

## Servidor
- Backend: `:8003` | Frontend: `:5178` | `ENABLE_BOTS=false`
- Arrancar: `./start.sh`
- Tests: `cd backend && /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/ -v`

---

## Lo que se implementó en este worktree

### Backend
- `backend/api/flows.py` — endpoint `GET /api/empresas/{empresa_id}/flow/graph`
  - Empresas con `flow_id="luganense"` → extrae grafo real de LangGraph (`app.get_graph()`)
  - Empresas sin `flow_id` → grafo sintético según `tool_tipo` (assistant por defecto)
  - Auth: acepta JWT empresa O x-password admin
- `backend/tests/test_flows.py` — 8 tests, todos pasando

### Frontend
- `frontend/src/components/FlowCanvas.jsx` — canvas React Flow con layout dagre automático
  - Colores por tipo de nodo: start/end/router/fetch/llm/reply/notify/summarize/generic
  - `@xyflow/react` + `dagre` instalados
- `EmpresaCard.jsx` — nueva tab "Flow" visible para todas las empresas

### phones.json
- `luganense` tiene `flow_id: "luganense"` para extraer su grafo LangGraph real

---

## Pendiente (Fase 2 — worktree futuro)

- Edición drag-drop: mover nodos, crear/eliminar edges desde la UI
- Eliminar la pestaña "Herramientas" (cuando Flow la reemplace del todo)
- Persistir topologías en DB
- Grafos Python mínimos para fixed_message/summarizer/assistant (Opción A)
- Labels en edges condicionales (scope_router → "noticias" / "oficio")

---

## Para mergear desde `_`
```bash
git merge feat-flow-ui
git push origin master
```
