# Plan: Refactor — UIs, Contactos como Flow, Conexiones como default heredable

**Fecha:** 2026-04-10  
**Estado:** Aprobado — pendiente de worktree

---

## Visión

El sistema actual mezcla responsabilidades en la solapa "Contactos" y tiene configuración de filtros duplicada entre la UI de conexiones y el nodo trigger.

El nuevo modelo:
- **Flows** son el motor central — todo comportamiento vive en flows compuestos de nodos pequeños
- **Nodos al estilo Unix** — composables, minimalistas, una sola responsabilidad cada uno
- **Conexiones** tienen una configuración default de filtro que los triggers heredan y pueden pisar
- **UIs** son vistas personalizadas por empresa, conectadas a datos generados por flows
- **Contactos** es la primera UI — su lógica de guardado vive en un flow propio

---

## Principio de diseño de nodos: Unix

> "Hacer una sola cosa y hacerla bien. Componer soluciones conectando nodos, no construir un nodo que haga todo."

El nodo `save_contact` no decide nada — solo guarda. La inteligencia de qué guardar y cuándo vive en nodos anteriores (router, estado, summarizer). Esto permite reutilizar esos nodos en otros contextos.

---

## Cambios al plan original

### 1. Nodo `save_contact` — tonto por diseño

El nodo recibe datos del FlowState y los persiste. No clasifica, no decide, no resume.

```python
config_schema = {
    "name_field":    str,  # clave del state donde leer el nombre. Default: "contact_name"
    "phone_field":   str,  # clave del state para el teléfono. Default: "contact_phone"
    "notes_field":   str,  # clave del state para notas/descripción. Default: "contact_notes"
    "update_if_exists": bool,  # si ya existe ese phone, actualizar en vez de duplicar
}
```

El `run()` solo llama a `db.create_contact()` o `db.update_contact()` con lo que encuentra en el state.

**La inteligencia está ANTES del nodo, en el flow:**

```
message_trigger
    ↓
Router LLM — ¿es una consulta de trabajo? (herrería / electricidad / otro oficio)
    → "no es trabajo" → termina (no guarda nada)
    → "herrería"      → SetState(trade="herrería")  → save_contact
    → "electricidad"  → SetState(trade="electricidad") → save_contact
```

El nodo `SetState` (o un campo del router) marca el dato en el estado antes de llegar a `save_contact`.

### 2. Conexiones — configuración default heredable (no "limpiar", empoderar)

Cada conexión gana un botón de configuración que abre el mismo `ContactFilterPicker` que hoy tiene el nodo `message_trigger`:
- Todos los conocidos / Desconocidos
- Incluir específicos
- Excluir siempre

**Sin cooldown** — el cooldown pertenece al nodo que envía el mensaje (send_message o equivalente), no al trigger ni a la conexión.

Además, debajo del filtro, aparece la lista de **sugeridos de esa conexión** con botón "Excluir" directo — sin tener que ir a la solapa Contactos. Excluir desde aquí agrega al `excluded` del default de la conexión.

**Jerarquía de herencia:**
```
Configuración de Conexión (default_filter)
    ↓ hereda
message_trigger del flow (puede pisar campo por campo)
```

Si el trigger tiene `contact_filter: null` → hereda el default de la conexión.  
Si el trigger tiene `contact_filter: {}` (aunque sea vacío) → usa ese valor y no hereda.

Esto evita que cada flow nuevo tenga que configurar desde cero los mismos filtros.

### 3. Flow piloto gm_herreria — clasificar consultas de trabajo

El flow "Contactos — GM Herrería" detecta si el mensaje indica una consulta de trabajo en alguno de los oficios de la empresa. Al arrancar: herrería y electricidad. La arquitectura permite agregar más oficios editando el flow.

```
message_trigger (5491124778975 — bot de gm_herreria)
    ↓
Router LLM — clasifica el mensaje:
    config: "¿El mensaje indica una consulta de trabajo?
             Si sí, qué oficio: herrería, electricidad, otro.
             Si no es consulta de trabajo, ruta: 'personal'"
    rutas: "herreria" | "electricidad" | "otro_oficio" | "personal"
    ↓
[rama herreria]  → SetState(trade="herrería")     → save_contact
[rama electric.] → SetState(trade="electricidad") → save_contact
[rama otro]      → SetState(trade="otro")         → save_contact
[rama personal]  → termina (no guarda)
```

`save_contact` guarda:
- phone: `state.contact_phone`
- name: `state.contact_name` (nombre WA si disponible)
- notes: `state.trade` (el oficio detectado)

### 4. Solapas EmpresaCard — resultado final

```
[Conexiones] [Flow] [UIs] [Configurar]
```

- **Conexiones**: gestión técnica (agregar/quitar bots, QR, status) + sección de configuración default de filtro por conexión (los mismos campos del trigger)
- **Flow**: lista de flows de la empresa (sin cambios)
- **UIs**: lista de UIs personalizadas. Primera: "Contactos" (lista de contactos + sugeridos con excluir)
- **Configurar**: configuración de la empresa (nombre, password, etc.)

La solapa "Contactos" actual **desaparece** — pasa a vivir dentro de "UIs".

---

## Fases de implementación

### Fase 1 — Nodo `save_contact` + nodo `set_state`

**Backend:**
- [ ] `backend/graphs/nodes/save_contact.py` — guarda contacto desde el state
- [ ] `backend/graphs/nodes/set_state.py` — permite poner un valor arbitrario en el state (ej: `state.trade = "herrería"`)
- [ ] Registrar ambos en `NODE_REGISTRY`
- [ ] Agregar al catálogo de nodos del frontend (solo el nombre/color/tipo)

**DB:**
- [ ] Agregar columna `notes TEXT` a la tabla `contacts` (migración simple)
- [ ] Actualizar `db.create_contact()` y `db.update_contact()` para recibir `notes`

**Sin frontend nuevo en esta fase** — los nodos aparecen solos en el catálogo del flow editor.

---

### Fase 2 — Configuración default de Conexión

**Backend:**
- [ ] Nuevo endpoint: `GET /empresas/{id}/connections/{conn_id}/filter-config`
- [ ] Nuevo endpoint: `PUT /empresas/{id}/connections/{conn_id}/filter-config`
- [ ] Guardar la config en `phones.json` bajo cada conexión (campo `default_filter`)
- [ ] El engine en `compiler.py`: si un trigger NO tiene `contact_filter` configurado, leer el default de la conexión

**Frontend:**
- [ ] En `ConnectionCard` (dentro de la solapa Conexiones), agregar botón "Configurar filtro" que expande un panel
- [ ] Panel reutiliza `ContactFilterPicker` (sin cooldown — ese campo no aplica aquí)
- [ ] Debajo del picker: lista de sugeridos de esa conexión con botón "Excluir" (agrega al `excluded` del default)
- [ ] Guardar al hacer click en "Guardar" del panel

---

### Fase 3 — Refactor EmpresaCard: solapa UIs

**Frontend:**
- [ ] Extraer el contenido de la solapa "Contactos" a `ContactsUI.jsx` (componente standalone)
- [ ] Crear `UIsList.jsx` — lista de UIs de la empresa
- [ ] En EmpresaCard: reemplazar solapa "Contactos" por solapa "UIs" que renderiza `UIsList`
- [ ] Por ahora, `UIsList` muestra solo la UI de contactos hardcodeada (sin tabla DB todavía)

**Nota:** La tabla `empresa_uis` en DB se puede agregar después — por ahora la UI de Contactos se muestra siempre (como hoy). La tabla se agrega cuando haya más de un tipo de UI.

---

### Fase 4 — Flow piloto gm_herreria

- [ ] Crear el flow "Contactos — GM Herrería" desde el editor
- [ ] Configurar el Router LLM con el prompt de clasificación de oficios
- [ ] Conectar las ramas con `set_state` → `save_contact`
- [ ] Verificar en la UI de Contactos que aparecen los contactos guardados con el campo "oficio"

---

## Worktree

Este trabajo **no requiere estar en prod/master** — se puede (y debe) hacer en un worktree dev:

```
worktree: refactor-ui-flows
backend: 8002
frontend: 5175
```

La única excepción es el **merge final a master**, que siempre hace la sesión de `_`.

Los riesgos son bajos:
- Las fases 1 y 2 son aditivas (no rompen nada existente)
- La fase 3 es un refactor de frontend puro (sin cambios de DB)
- La fase 4 es un flow nuevo (no toca código)

---

## Lo que NO cambia

- La tabla `contacts` y `contact_channels` en DB — solo se agrega columna `notes`
- El engine `compiler.py` — solo se agrega lógica de herencia de config (aditivo)
- El nodo `message_trigger` — sigue siendo la fuente de verdad, ahora con herencia
- La lista `excluded` en el trigger — sigue siendo el mecanismo correcto para silenciar
- Los sugeridos y el botón "Excluir" implementados hoy — compatibles, no cambian

---

## Notas de diseño

- **Cooldown**: pertenece al nodo que envía el mensaje (send_message o llm_reply), no al trigger ni a la conexión. El trigger solo decide si el flow corre — no cuándo responde.
- **`set_state` vs. salida del router**: el router puede setear la ruta, pero para datos arbitrarios como el oficio detectado conviene un nodo `set_state` explícito. Alternativamente, el Router LLM puede extenderse para escribir en campos del state además de la ruta — a definir en la implementación.
- **`notes` en contactos**: campo de texto libre. El flow de gm_herreria pondrá "herrería" o "electricidad", pero podría ser cualquier texto. No es un enum.
- **Herencia de filter-config**: si el trigger tiene `contact_filter: null` (vacío, sin configurar), hereda el default de la conexión. Si tiene algún valor (aunque sea vacío `{}`), usa ese valor y no hereda. Esto permite que un trigger opte por "sin filtro" explícitamente.
- **Sugeridos en la conexión**: los sugeridos se filtran por `connection_id` de esa conexión, no por empresa completa. Excluir desde aquí modifica el `default_filter.excluded` de la conexión en `phones.json`.
