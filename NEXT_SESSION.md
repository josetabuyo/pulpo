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
- 21 tests pasando

Archivos clave ya implementados:
- `backend/api/flows.py` — GET /flow/node-types + GET grafo
- `backend/graphs/node_types.py` — registro de tipos (fuente de verdad)
- `frontend/src/components/FlowCanvas.jsx` — canvas read-only

---

## Próxima tarea: Fase 1 — DB + API de flows

**Objetivo:** crear la infraestructura de persistencia para que los flows vivan en DB
en lugar de estar hardcodeados en Python.

### Pasos concretos

1. **Migración DB** (`backend/db.py`)
   - Crear tabla `flows` con columnas: `id, empresa_id, name, definition (JSON), connection_id, contact_phone, active, created_at, updated_at`
   - La migration debe ser compatible con la DB existente (no romper tools todavía)

2. **Endpoints CRUD** (`backend/api/flows.py`)
   - `GET  /api/empresas/{id}/flows` — lista de flows de la empresa
   - `POST /api/empresas/{id}/flows` — crear nuevo flow (con definition vacía o template)
   - `GET  /api/empresas/{id}/flows/{flow_id}` — detalle con definition completa
   - `PUT  /api/empresas/{id}/flows/{flow_id}` — guardar definition (topología + config de nodos)
   - `DELETE /api/empresas/{id}/flows/{flow_id}` — eliminar

3. **Migrar Luganense a DB**
   - Crear un flow en DB para Luganense con la definition actual del grafo
   - El endpoint GET grafo existente puede ahora leer de DB en lugar de hardcoded

4. **Tests** (`backend/tests/test_flows.py`)
   - Agregar tests para los nuevos endpoints CRUD
   - Verificar que la migration no rompe los 21 tests existentes

### Regla: backward-compat durante esta fase
- La tabla `tools` sigue existiendo
- El auto-reply sigue leyendo `tools` como antes
- No tocar la lógica de ejecución todavía — solo persistencia

---

## Regla de esta sesión

Al terminar: **commit en feat-flow-ui → avisar a la sesión de `_` para merge a master → push → restart backend de producción**.
