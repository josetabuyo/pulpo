# Plan: message_trigger como única fuente de verdad

**Creado:** 2026-04-08  
**Filosofía:** Data-driven LEAN — la config vive donde tiene sentido semántico, no donde es conveniente implementarla.

---

## El problema actual

`connection_id` y `contact_filter` viven en **tres lugares**:

1. Columna `connection_id` en la tabla `flows` (DB)
2. Columna `contact_filter` en la tabla `flows` (DB)
3. Config del nodo `message_trigger` en el JSON `definition`

El backend los inyecta del nivel de flow al nodo en cada guardado. El frontend los edita en el FlowHeader (barra superior), que es conceptualmente el nivel del flow.

**Consecuencias:**
- Fuentes que se desincroniza n si el guardado falla parcialmente
- El FlowHeader asume un único trigger por flow
- El concepto "filtro de contactos" no tiene hogar claro
- Futuro multi-trigger (reloj, sensor físico, etc.) es imposible con este modelo

---

## Visión

El nodo `message_trigger` **es** el trigger. Todo lo que configura cómo y cuándo se activa el flow vive ahí. Las tabs "Conexiones" y "Contactos" son los UIs de administración de esas entidades — y en el futuro podrían eliminarse, porque la única razón de existir es configurar propiedades de nodos trigger.

```
Flow
 └── [message_trigger]  ←── connection_id aquí
      ├── config.connection_id
      ├── config.contact_filter
      │    ├── include_all_known
      │    ├── include_unknown
      │    ├── included[]     ← nombres o teléfonos
      │    └── excluded[]
      └── config.created_at  ← (ya existe: guard anti-retroactivo)
 └── [router]
 └── [llm]
 └── ...
```

---

## Alineación con planes existentes

- **PLAN_FLOW_NODES.md Fase 1 y 5**: ya planifica mover `connection_id` al nodo `input_text` (renombrado `message_trigger`). Este plan es la implementación concreta de ese principio.
- **PLAN_FLOW_NODES.md Fase 5**: eliminar la columna `connection_id` de la tabla `flows`. Este plan la mantiene temporalmente como cache indexada, con eliminación diferida.
- **No contradice ningún plan existente**.

---

## Qué cambia

### Backend (mínimo, ya casi está)

**Hoy:**
- `resolve_flows()` filtra por `connection_id` SQL
- `execute_flow()` lee `contact_filter` del dict de flow (nivel tabla)
- El endpoint `PUT /flows/{id}` inyecta `connection_id` y `contact_filter` en el nodo

**Target:**
- `resolve_flows()` devuelve todos los flows activos de la empresa (sin filtrar por `connection_id` en SQL)
- `execute_flow()` lee `connection_id` y `contact_filter` **del nodo** `message_trigger`
- El endpoint `PUT /flows/{id}` **no inyecta nada**: guarda la `definition` tal cual llega
- La columna `connection_id` en `flows` queda como cache (populated desde el nodo al guardar), usada solo para queries de administración, no para filtrado de ejecución
- La columna `contact_filter` en `flows` **se elimina** (redundante con el nodo)

**Guard anti-retroactivo**: ya existe en `compiler.py` — el `created_at` del flow es el timestamp mínimo para procesar mensajes. Intocable.

### Frontend

**Hoy:**
```
FlowHeader
 ├── input: Nombre
 ├── select: Conexión        ← SACAR
 ├── picker: Filtro contactos ← SACAR
 └── button: Guardar
```

**Target:**
```
FlowHeader
 ├── input: Nombre
 └── button: Guardar
```

El `message_trigger` se configura en **NodeConfigPanel** (doble clic en el nodo), igual que cualquier otro nodo. Su panel de config es más rico:

```
┌─────────────────────────────────────┐
│  Trigger de mensaje                 │
├─────────────────────────────────────┤
│  Conexión                           │
│  [select con las conexiones] [→]    │
│  → abre el tab Conexiones embebido  │
├─────────────────────────────────────┤
│  Contactos                          │
│  [ContactFilterPicker]    [→]       │
│  → abre el tab Contactos embebido   │
└─────────────────────────────────────┘
```

El botón `→` abre un modal/drawer con el UI completo del tab (conexiones o contactos), igual al que el usuario ya conoce. No es una re-implementación — es el mismo componente embebido.

### Multi-trigger

Con este modelo, un flow puede tener **dos** nodos `message_trigger` independientes:

```
[trigger WA — conexión 75]    [trigger TG — sesión oficial]
         └───────────────┬───────────────┘
                      [router]
                      /      \
                   [llm]   [reply]
```

El engine evalúa cada trigger independientemente. Si el mensaje matchea el trigger WA, ejecuta desde ahí. Si matchea el TG, desde ahí. Ambos pueden converger en el mismo flujo posterior.

---

## Fases de implementación

### Fase 1 — Backend: engine lee del nodo, no de la columna

**Cambios en `compiler.py`:**
- `resolve_flows()`: ya no filtra por `connection_id` en SQL. Retorna todos los flows activos.
- `execute_flow()`: busca el/los nodo(s) `message_trigger` en la definition. Para cada uno, evalúa si `config.connection_id` matchea el `connection_id` entrante y si el contacto pasa el `contact_filter`. Si ningún trigger matchea → skip.
- El engine soporta múltiples nodos `message_trigger` en el mismo flow (evalúa todos, usa el primero que matchea como punto de entrada BFS).

**Cambios en `api/flows.py`:**
- Eliminar la inyección de `connection_id` y `contact_filter` en el nodo en el `PUT`. El endpoint guarda la `definition` as-is.
- Mantener la columna `connection_id` en DB como cache: al guardar, leer el `connection_id` del primer nodo `message_trigger` y escribirlo en la columna (para que el admin pueda ver a qué conexión pertenece cada flow sin parsear el JSON).
- Eliminar la columna `contact_filter` de la tabla (ya no tiene sentido como dato duplicado).

**Tests:**
- `test_engine_lee_trigger_del_nodo`: flow con `message_trigger.config.connection_id = "X"` no responde a mensajes de "Y" aunque la columna diga otra cosa
- `test_engine_multi_trigger`: flow con dos triggers, uno WA y uno TG, responde correctamente desde cada canal
- `test_engine_contact_filter_del_nodo`: filtro de contactos del nodo se aplica correctamente

### Fase 2 — Frontend: sacar del FlowHeader, agregar al NodeConfigPanel

**Cambios en `FlowHeader.jsx`:**
- Eliminar el `<select>` de conexión
- Eliminar el `<ContactFilterPicker>`
- Eliminar el estado `connectionId` y `contactFilter`
- El `PUT` ya no envía `connection_id` ni `contact_filter` al nivel de flow
- El `PUT` envía solo `name` y `definition`

**Cambios en `NodeConfigPanel.jsx`:**
- Agregar render especial para tipo `message_trigger`
- Panel con dos secciones:
  - **Conexión**: `<select>` con las conexiones de la empresa + botón `→` para abrir modal con el UI completo de Conexiones
  - **Filtro de contactos**: `ContactFilterPicker` (mover desde FlowHeader) + botón `→` para abrir modal con el UI completo de Contactos

**Cambios en el schema del nodo `message_trigger`:**
- `NodeConfigPanel` renderiza el panel custom para este tipo (como excepción al schema genérico)
- Al cambiar la conexión o el filtro, `updateNodeConfig()` en el store actualiza `data.config` del nodo → queda marcado como dirty → se guarda junto con la `definition` al hacer Guardar

**Tests Playwright:**
- Doble clic en trigger → panel muestra conexión y filtro de contactos
- Cambiar conexión en panel → al guardar, la definition en DB refleja el cambio

### Fase 3 — Eliminar columna `contact_filter` de la tabla flows

**DB migration:**
```sql
ALTER TABLE flows DROP COLUMN contact_filter;
```

**Backend:**
- `_flow_row_to_dict`: no intenta leer `contact_filter` de la fila
- `update_flow`: no acepta ni guarda `contact_filter` como campo de primer nivel
- `get_flows` / `get_flow`: no retornan `contact_filter` como campo de primer nivel (viene dentro de `definition`)

**No urgente**: puede hacerse después de que Fase 2 esté estable en producción.

---

## Lo que NO hacemos ahora

- **No eliminar las tabs Conexiones y Contactos**: siguen siendo el admin UI de esas entidades. Futura decisión.
- **No crear otros tipos de trigger** (clock, sensor físico, etc.): YAGNI. La arquitectura los soporta, pero no se implementan sin caso concreto.
- **No implementar semáforos en flows**: el multi-trigger básico (Fase 1) es suficiente para ahora.
- **No eliminar la columna `connection_id`** de `flows` todavía: se usa para listar flows en la UI admin. Puede eliminarse cuando el editor muestra el trigger como parte del canvas y la columna es redundante.

---

## Estado

| Fase | Estado |
|------|--------|
| Fase 1 — Backend engine desde el nodo | ⬜ Pendiente |
| Fase 2 — Frontend: panel del nodo | ⬜ Pendiente |
| Fase 3 — Eliminar columna contact_filter | ⬜ Pendiente (después de Fase 2 en prod) |

---

## Worktree sugerido

```
/Users/josetabuyo/Development/pulpo/feat-trigger-node
BACKEND_PORT=8001
FRONTEND_PORT=5174
```

Arrancar por **Fase 1 backend** — es el cambio más seguro (no rompe nada en prod inmediatamente) y desbloquea la Fase 2 frontend.
