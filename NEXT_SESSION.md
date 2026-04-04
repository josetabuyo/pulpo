# NEXT_SESSION — feat-flow-ui

## TL;DR
Dos tareas concretas: (1) arreglar flows vacíos en master, (2) eliminar tab "Herramientas" legacy.
El plan completo está en: `management/PLAN_FLOW_EDITOR.md`

---

## Servidor
- Backend: `:8003` | Frontend: `:5178` | `ENABLE_BOTS=false`
- Arrancar: `cd /Users/josetabuyo/Development/pulpo/feat-flow-ui && ./start.sh`
- Tests: `cd backend && /Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/ -v`
- **106 tests pasando** — todos verdes antes de empezar

---

## Estado actual: Fases 0, 1, 2, 3 COMPLETAS

### Lo que está hecho

#### Arquitectura de nodos
- `backend/graphs/nodes/state.py` — `FlowState` (incluye `from_delta_sync`, `timestamp`)
- `backend/graphs/nodes/base.py` — `BaseNode`
- `backend/graphs/nodes/reply.py`, `llm_respond.py`, `summarize.py`, `luganense_flow.py`
- `backend/graphs/nodes/__init__.py` — `NODE_REGISTRY` central
- `backend/graphs/compiler.py` — `execute_flow()`, `resolve_flows()`, `run_flows()`

#### Adaptadores (WA / Telegram / Sim usan `run_flows`)
- `backend/sim.py`, `backend/bots/telegram_bot.py`, `backend/automation/whatsapp.py`
- `backend/api/whatsapp.py` — `_run_delta_sync` usa `run_flows(from_delta_sync=True)`

#### DB + API CRUD de flows
- Tabla `flows` en `backend/db.py`
- `backend/api/flows.py` — GET list, POST, GET detail, PUT, DELETE
- `seed_default_flows()` crea flows iniciales al arrancar

#### Editor drag & drop (Fase 2)
- `frontend/src/store/flowStore.js` — Zustand store
- `frontend/src/components/FlowList.jsx`, `FlowEditor.jsx`, `NodePalette.jsx`
- `frontend/src/components/FlowCanvas.jsx`, `NodeConfigPanel.jsx`, `FlowHeader.jsx`
- **106 backend tests + 24/25 Playwright tests pasando**

---

## Tarea 1 — Fix flows vacíos en master (URGENTE)

### Root cause

`seed_default_flows()` tiene un **bug silencioso**: si un bot no tiene ni `flow_id`
ni `tool_tipo`, cae fuera de todos los `if/elif` y no se crea ningún flow.
Peor: si el bot YA fue procesado (incluso sin crear flow), `flow_exists_for_empresa`
devuelve True en la próxima llamada y nunca lo reintenta.

Esto explica por qué en master hay bots sin flows.

### Diagnóstico para master (lo hace el agente `_`)

Desde master, correr en `qdb`:
```sql
SELECT empresa_id, name, active FROM flows;
```
Si hay bots de phones.json que no aparecen → confirmado el bug.

### Fix en este worktree

**1. Agregar fallback en `seed_default_flows`** (`backend/api/flows.py`):

Al final del bloque `if/elif`, agregar:
```python
else:
    # Bot sin tool_tipo ni flow_id conocido → flow mínimo (reply vacío como placeholder)
    definition = {
        "nodes": [
            {"id": "__start__", "type": "start", "position": {"x": 250, "y": 50},  "config": {}},
            {"id": "reply",     "type": "reply", "position": {"x": 250, "y": 200}, "config": {"message": ""}},
            {"id": "__end__",   "type": "end",   "position": {"x": 250, "y": 350}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "__start__", "target": "reply",   "label": None},
            {"id": "e2", "source": "reply",     "target": "__end__", "label": None},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    await db.create_flow(empresa_id, bot.get("name", empresa_id), definition)
```

**2. Agregar endpoint de re-seed forzado** (`backend/api/flows.py`):

```python
@router.post("/flows/reseed", dependencies=[Depends(require_admin)])
async def reseed_flows():
    """Re-corre el seed ignorando el chequeo de existencia. Útil para fix en prod."""
    from api.flows import seed_default_flows
    # seed_default_flows usa flow_exists_for_empresa que evita duplicados por empresa_id
    # Para forzar re-seed de bots que no tienen flow, necesitamos que no existan aún.
    # Si existen flows pero vacíos: este endpoint los deja como están (no sobrescribe).
    await seed_default_flows()
    return {"ok": True}
```

Nota: si master ya tiene bots "existentes" con flows vacíos/rotos, el admin
necesitará borrarlos manualmente vía `DELETE /api/empresas/{id}/flows/{flow_id}`
antes de que el reseed los recree. Documentar esto.

**3. Agregar test** para el caso de bot sin `tool_tipo` ni `flow_id`:
```python
# tests/test_flows.py
async def test_seed_creates_flow_for_bot_without_tool_tipo():
    # bot = {"id": "bot_sin_tipo", "name": "Test"}
    # seed debe crear un flow de reply vacío
```

---

## Tarea 2 — Eliminar tab "Herramientas" legacy

### Qué borrar en `frontend/src/components/EmpresaCard.jsx`

El archivo tiene **~150 líneas** de lógica legacy. Borrar:

1. **Estado**: `tools`, `setTools`, `toolModal`, `setToolModal`
2. **Efectos**: `useEffect` que carga `/api/empresas/${botId}/tools`
3. **Handlers**: `handleToolToggle`, `handleDeleteTool`, `handleSaveTool`
4. **Variables derivadas**: `visibleTools`, `activeToolsCount`, `toolsTabCount`
5. **Tab en la lista**: `{ id: 'tools', label: 'Herramientas', count: toolsTabCount }` → eliminar
6. **Bloque JSX**: `{activeTab === 'tools' && (...)}` → eliminar todo
7. **Componente `ToolModal`**: si está inline en el archivo, borrarlo completo
8. **Import no usado**: cualquier import que solo usaba la sección tools

### Verificar antes de borrar
Que la tab "Flows" ya tiene:
- ✅ Lista de flows con nombres
- ✅ Crear / editar / borrar flow
- ✅ Asignar a contacto específico (FlowHeader)
- ✅ Toggle activo/inactivo (campo `active` — verificar que FlowList lo muestra)

Si FlowList **no muestra toggle activo/inactivo**, agregarlo antes de borrar Herramientas.

### Limpiar backend de `tool_tipo`

En `backend/api/flows.py`, el endpoint `GET /empresas/{id}/flow/graph` (línea ~339)
aún lee `tool_tipo` de phones.json para el grafo visual read-only legacy.
Una vez que todos los bots tienen flows en DB, este endpoint puede simplificarse:
- Si hay flows en DB → retornar el primero
- Si no hay → retornar grafo vacío (no leer phones.json)

---

## Orden de ejecución

1. Correr tests base para confirmar verde (106 pasando)
2. Fix seed + fallback + test nuevo → confirmar tests siguen verde
3. Agregar endpoint `/flows/reseed`
4. Eliminar tab Herramientas de EmpresaCard (verificar toggle activo primero)
5. Limpiar endpoint `flow/graph` de dependencia tool_tipo
6. Tests Playwright: verificar que la tab Flows sigue funcionando sin Herramientas
7. Commit → avisar a master para merge + reseed en producción

---

## Regla de esta sesión

Al terminar: **commit en feat-flow-ui → avisar que está listo para merge a master**.
El merge a master y push a origin siempre lo hace la sesión de `_` (producción).
Después del merge, master debe correr `POST /api/flows/reseed` para poblar los flows vacíos.
