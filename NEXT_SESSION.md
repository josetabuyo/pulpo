# NEXT_SESSION — feat-flow-ui

## TL;DR
Continuar desarrollo del Flow Editor. El plan completo está en:
`management/PLAN_FLOW_EDITOR.md`

---

## Servidor
- Backend: `:8003` | Frontend: `:5178` | `ENABLE_BOTS=false`
- Arrancar: `cd /Users/josetabuyo/Development/pulpo/feat-flow-ui && ./start.sh`
- Tests: `cd backend && /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/ -v`
- **106 tests pasando** — todos verdes antes de empezar

---

## Estado actual: Fases 0, 1, 2 COMPLETAS

### Lo que está hecho

#### Arquitectura de nodos (nueva — reemplaza sistema "tools")
- `backend/graphs/nodes/state.py` — `FlowState` dataclass
- `backend/graphs/nodes/base.py` — `BaseNode` con `__init__(config)` + `async def run(state)`
- `backend/graphs/nodes/reply.py`, `llm_respond.py`, `summarize.py`, `luganense_flow.py`
- `backend/graphs/nodes/__init__.py` — `NODE_REGISTRY` central
- `backend/graphs/compiler.py` — `execute_flow()`, `resolve_flows()`, `run_flows()`

#### Adaptadores de conexión (WA / Telegram usan `run_flows`)
- `backend/sim.py`, `backend/bots/telegram_bot.py`, `backend/automation/whatsapp.py`

#### DB + API CRUD de flows
- Tabla `flows` en `backend/db.py` (con migration)
- `backend/api/flows.py` — GET list, POST, GET detail, PUT, DELETE
- `seed_default_flows()` crea flows iniciales desde `phones.json` al arrancar

#### Editor drag & drop (Fase 2 — COMPLETA)
- `frontend/src/store/flowStore.js` — Zustand store (nodes, edges, selectedNodeId, isDirty)
- `frontend/src/components/FlowList.jsx` — lista de flows con acciones CRUD
- `frontend/src/components/FlowEditor.jsx` — contenedor del editor
- `frontend/src/components/NodePalette.jsx` — sidebar con tipos de nodo arrastrables
- `frontend/src/components/FlowCanvas.jsx` — canvas editable (drag, connect, delete)
- `frontend/src/components/NodeConfigPanel.jsx` — formularios por tipo (reply, llm_respond)
- `frontend/src/components/FlowHeader.jsx` — nombre, connection, contact, guardar
- `frontend/playwright.config.cjs` — lee puerto del .env del worktree (no hardcodeado)
- `frontend/tests/flows.spec.cjs` — 6 tests E2E del editor, todos verdes
- **106 backend tests + 24/25 Playwright tests pasando**
  (1 test preexistente falla: badge SIM — no relacionado con flows)

---

## Próxima tarea: Fase 3 — Delta sync unificado

El usuario pidió que delta sync use el mismo pipeline que mensajes en tiempo real (`_on_message`).
Actualmente delta sync llama a `_accumulate_msg` directamente, saltándose los flows.

**Scope:**
- Refactorizar `_run_delta_sync` en `automation/whatsapp.py` para llamar `run_flows` en vez de `_accumulate_msg`
- Pasar `from_poll=True` en el `FlowState` para que `SummarizeNode` sepa que es histórico
- Misma lógica que real-time: un mensaje a la vez, mismo pipeline

---

## Regla de esta sesión

Al terminar: **commit en feat-flow-ui → avisar que está listo para merge a master**.
El merge a master y push a origin siempre lo hace la sesión de `_` (producción).
