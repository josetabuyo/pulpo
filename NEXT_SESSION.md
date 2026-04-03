# NEXT_SESSION — feat-flow-ui

## TL;DR
**Lee el plan completo antes de arrancar:**
`management/PLAN_FLOW_EDITOR.md`

El plan tiene la visión completa, el catálogo de nodos, el esquema de DB,
la arquitectura frontend y la hoja de ruta por fases.

---

## Servidor
- Backend: `:8003` | Frontend: `:5178` | `ENABLE_BOTS=false`
- Arrancar: `./start.sh`
- Tests: `cd backend && /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/ -v`

---

## Estado actual (Fase 0 completa)

La Fase 0 está en producción:
- Tab "Flow" en EmpresaCard con canvas React Flow + dagre
- Grafo real de Luganense vía `app.get_graph()`
- Grafos sintéticos para fixed_message/summarizer/assistant
- Labels muestran nombre del nodo (no tipo genérico)
- 118 tests pasando

Archivos clave ya implementados:
- `backend/api/flows.py` — GET /flow/node-types + GET grafo
- `backend/graphs/node_types.py` — registro de tipos (fuente de verdad)
- `frontend/src/components/FlowCanvas.jsx` — canvas read-only

---

## Próxima tarea: Fase 1 — DB + API de flows

Ver `management/PLAN_FLOW_EDITOR.md` sección "Fase 1".

Scope mínimo:
1. Crear tabla `flows` en DB (`backend/db.py`)
2. Endpoints CRUD en `backend/api/flows.py`
3. Migrar Luganense de phones.json a DB
4. Tests en `backend/tests/test_flows.py`
5. Backward-compat: tabla `tools` sigue igual

---

## Regla de esta sesión

Al terminar: **commit en feat-flow-ui → avisar a la sesión de `_` para merge a master → push → restart backend de producción**.
