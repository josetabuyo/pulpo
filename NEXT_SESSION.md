# NEXT_SESSION — refactor-ui-flows

**Worktree:** `/Users/josetabuyo/Development/pulpo/refactor-ui-flows`
**Branch:** `refactor-ui-flows`
**Backend:** http://localhost:8002
**Frontend:** http://localhost:5175
**Modo:** simulado (ENABLE_BOTS=false) — usar simulador para probar flows

---

## Objetivo

Implementar el plan `management/PLAN_REFACTOR_UI_CONTACTOS_FLOWS.md` en 4 fases.

---

## Arrancar

```bash
cd /Users/josetabuyo/Development/pulpo/refactor-ui-flows
./start.sh
```

Correr tests primero:
```bash
cd backend && pytest tests/ -v
```

---

## Fase 1 — Nodo `save_contact` + nodo `set_state` (BACKEND)

### 1a. Migración DB: columna `notes` en `contacts`

En `backend/db.py`:
- Agregar `notes TEXT` a la tabla `contacts` en `init_db()`
- Migración lazy en `init_db()`: `ALTER TABLE contacts ADD COLUMN notes TEXT` con try/except
- Actualizar `create_contact(bot_id, name, notes=None)` y `update_contact(contact_id, name, notes=None)`
- Actualizar `get_contact()` y `get_contacts()` para incluir `notes` en el dict retornado

### 1b. Nodo `set_state`

Archivo: `backend/graphs/nodes/set_state.py`

Escribe un valor fijo en un campo del FlowState. Útil para marcar datos antes de `save_contact`.

```python
class SetStateNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        field = self.config.get("field", "").strip()
        value = self.config.get("value", "")
        if field:
            if hasattr(state, field):
                setattr(state, field, value)
            else:
                if state.extra is None:
                    state.extra = {}
                state.extra[field] = value
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "field": {"type": "string", "label": "Campo del estado", "hint": "Ej: contact_notes", "required": True},
            "value": {"type": "string", "label": "Valor a escribir", "required": True},
        }
```

Agregar `extra: dict | None = None` a `FlowState` en `backend/graphs/nodes/state.py`.

### 1c. Nodo `save_contact`

Archivo: `backend/graphs/nodes/save_contact.py`

Tonto por diseño: solo persiste lo que ya está en el FlowState. No decide cuándo guardar.

```python
class SaveContactNode(BaseNode):
    async def run(self, state: FlowState) -> FlowState:
        empresa_id = state.empresa_id or ""
        name_field  = self.config.get("name_field",  "contact_name")
        phone_field = self.config.get("phone_field", "contact_phone")
        notes_field = self.config.get("notes_field", "contact_notes")
        update      = self.config.get("update_if_exists", True)

        # Leer del state o del dict extra
        def _get(field):
            v = getattr(state, field, None)
            if v: return v
            return (state.extra or {}).get(field)

        name  = _get(name_field)  or state.contact_phone
        phone = _get(phone_field) or state.contact_phone
        notes = _get(notes_field)

        if not name or not empresa_id:
            return state

        import db
        existing = await db.find_contact_by_channel("whatsapp", phone) if phone else None
        if existing and update:
            await db.update_contact(existing["id"], name, notes=notes)
        elif not existing:
            contact_id = await db.create_contact(empresa_id, name, notes=notes)
            if phone:
                try:
                    await db.add_channel(contact_id, "whatsapp", phone)
                except Exception:
                    pass
        return state

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "name_field":        {"type": "string", "label": "Campo → nombre",    "default": "contact_name"},
            "phone_field":       {"type": "string", "label": "Campo → teléfono",  "default": "contact_phone"},
            "notes_field":       {"type": "string", "label": "Campo → notas",     "default": "contact_notes", "hint": "Ej: trade, category"},
            "update_if_exists":  {"type": "bool",   "label": "Actualizar si ya existe", "default": True},
        }
```

### 1d. Registrar en NODE_REGISTRY

En `backend/graphs/nodes/__init__.py`:
```python
from .set_state    import SetStateNode
from .save_contact import SaveContactNode

NODE_REGISTRY = {
    ...existentes...,
    "set_state":    SetStateNode,
    "save_contact": SaveContactNode,
}
```

### 1e. Catálogo frontend

En `frontend/src/components/FlowEditor.jsx` (o donde esté la lista de nodos del panel izquierdo), agregar:
```js
{ type: 'set_state',    label: 'Establecer estado', color: '#0891b2' },
{ type: 'save_contact', label: 'Guardar contacto',  color: '#059669' },
```

---

## Fase 2 — Configuración default de Conexión (herencia en trigger)

### 2a. `default_filter` en phones.json

Estructura por conexión en phones.json:
```json
{
  "empresas": [{
    "phones": [{
      "number": "549...",
      "default_filter": {
        "include_all_known": false,
        "include_unknown": false,
        "included": [],
        "excluded": ["Colo", "Enzo grandi"]
      }
    }]
  }]
}
```

Nuevos endpoints en `backend/api/connections.py` (o crear `backend/api/connection_config.py`):
- `GET  /empresas/{id}/connections/{conn_id}/filter-config`
- `PUT  /empresas/{id}/connections/{conn_id}/filter-config`

### 2b. Herencia en el engine

En `backend/graphs/compiler.py`, en `execute_flow()`, donde se resuelve `contact_filter`:

```python
# Herencia: si el trigger no tiene contact_filter, tomar el default de la conexión
if entry_type == "message_trigger" and entry_config.get("contact_filter") is None:
    from config import get_connection_default_filter
    default_cf = get_connection_default_filter(entry_config.get("connection_id", ""))
    if default_cf:
        entry_config = {**entry_config, "contact_filter": default_cf}
```

Agregar `get_connection_default_filter(conn_id: str) -> dict | None` en `backend/config.py`.

### 2c. Panel de filtro por conexión en EmpresaCard

En `EmpresaCard.jsx`, en el componente de cada fila de conexión WA:
- Botón "⚙ Filtro" (o ícono) que expande un panel inline
- Panel: `ContactFilterPicker` (reusar el existente, SIN campo cooldown_hours)
- Debajo del picker: lista de sugeridos de ESA conexión (filtrados por connection_id) con botón "Excluir"
- "Excluir" agrega al `default_filter.excluded` y guarda via PUT inmediatamente
- Botón "Guardar" para el resto del filtro

---

## Fase 3 — Refactor EmpresaCard: solapa UIs

### 3a. Extraer a ContactsUI.jsx

Crear `frontend/src/components/ContactsUI.jsx` moviendo todo el contenido actual de la solapa "Contactos":
- Tabla de contactos con editar/eliminar
- Sugeridos (con separador has_messages, botón Agregar, Excluir, Agregar todos, Limpiar)
- Modal ContactModal

Props: `{ botId, apiCall, waConns, contacts, suggested, ... }` — o manejar el estado internamente.

### 3b. Crear UIsList.jsx

`frontend/src/components/UIsList.jsx`:
- Hardcodeado por ahora: muestra siempre la card "Contactos" con ícono y descripción
- Al clickear: renderiza `ContactsUI` inline
- Preparado para agregar más UIs en el futuro (estructura de lista + componente por tipo)

### 3c. Reemplazar solapa en EmpresaCard

```jsx
// Cambiar en el array de tabs:
{ id: 'uis', label: 'UIs', count: null }
// (eliminar el de 'contacts')

// Cambiar en el render:
{activeTab === 'uis' && <UIsList botId={botId} apiCall={apiCall} waConns={waConns} />}
```

Limpiar todo el estado y código de la solapa contacts del componente EmpresaCard (contacts, suggested, contactModal, showSuggested, importing, etc.) — ahora viven en ContactsUI.

---

## Fase 4 — Flow piloto (desde el editor, no requiere código)

Una vez que los nodos están disponibles, crear manualmente desde el editor:

**Flow: "Contactos — GM Herrería"**
- Trigger: connection_id = `5491124778975`
- Router LLM con prompt: "¿El mensaje indica una consulta de trabajo? Si sí, qué oficio: herrería, electricidad, otro_oficio. Si no es laboral, ruta: personal."
- Ramas: "herrería" → set_state(field=contact_notes, value=herrería) → save_contact
- Ramas: "electricidad" → set_state(field=contact_notes, value=electricidad) → save_contact
- Ramas: "otro_oficio" → set_state(field=contact_notes, value=otro) → save_contact
- Rama: "personal" → termina (sin guardar)

---

## Merge

El merge a master lo hace SIEMPRE la sesión de `_` (producción).
Cuando termines todas las fases, avisá: "listo para merge desde refactor-ui-flows".
