# Plan: Contactos por empresa

## Objetivo

Reemplazar el `allowedContacts[]` (array de strings en `phones.json`) por una lista de contactos real en la base de datos, con nombre + canales (WA, Telegram, email futuro), y unificar las conversaciones por contacto sin importar desde qué canal llegaron.

## Por qué

- Hoy los contactos son strings sueltos en el JSON — frágil y sin estructura
- No hay forma de ver con quién habló cada empresa
- Si el mismo contacto escribe por WA y por Telegram, son registros separados sin relación

---

## Modelo de datos

```
Contacto
  ├── id
  ├── empresa_id (bot_id)
  ├── nombre
  └── canales[]
        ├── type: "whatsapp" | "telegram" | "email"
        └── value: número / username / email

Conversación
  ├── id
  ├── empresa_id
  ├── contacto_id
  └── mensajes[]
        ├── channel
        ├── direction: "in" | "out"
        ├── body
        └── timestamp
```

### Tablas SQLite

```sql
CREATE TABLE contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contact_channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK(type IN ('whatsapp', 'telegram')),
  value TEXT NOT NULL,
  UNIQUE(type, value)
);
```

---

## Herramientas por conexión (prerequisito al modelo de contactos)

### Problema actual

Hoy cada bot tiene una sola herramienta de tipo "mensaje fijo" y una lista plana de contactos permitidos. No hay forma de tener comportamientos diferentes para distintos grupos de contactos, ni de tener más de una respuesta automática.

### Concepto: Herramienta (Tool)

Una **herramienta** es una unidad de comportamiento asignada a una o varias conexiones (bots). El primer tipo es "mensaje fijo" (`fixed_message`), pero el modelo debe soportar más tipos en el futuro (IA, webhook, etc.).

Cada herramienta tiene:

| Campo | Descripción |
|-------|-------------|
| `tipo` | `fixed_message` \| (futuro: `ai_agent`, `webhook`, ...) |
| `conexiones` | Lista de bot_ids a los que aplica. Si está vacío = todas las conexiones de la empresa |
| `contactos_incluidos` | Lista de contact_ids. Solo estos contactos activan la herramienta |
| `contactos_excluidos` | Lista de contact_ids que nunca activan esta herramienta |
| `incluir_desconocidos` | `bool` — si aplica a contactos que no están en la DB |
| `exclusiva` | `bool` — si es `true`, no puede coexistir otra herramienta exclusiva activa para el mismo bot+contacto |
| `activa` | `bool` — encendido/apagado sin borrar |

### Regla de resolución al recibir un mensaje

Cuando llega un mensaje de un contacto a un bot, el sistema evalúa **en orden** las herramientas activas de ese bot:

1. Si el contacto está en `contactos_excluidos` → saltar esta herramienta
2. Si el contacto está en `contactos_incluidos` → activar
3. Si el contacto es desconocido (no está en DB) y `incluir_desconocidos = true` → activar
4. Si `contactos_incluidos` está vacío y `incluir_desconocidos = true` → activar para todos
5. En cualquier otro caso → no aplica

### Conexiones compartidas entre empresas

Una misma conexión (número de teléfono / bot) puede pertenecer a **más de una empresa**. Por ejemplo, el número personal de un operador puede estar asignado a Empresa A para un grupo de contactos, y a Empresa B para otro grupo diferente.

Esto implica que:

- La relación entre conexiones y empresas es **muchos a muchos**
- La tabla `tool_connections` referencia `bot_id` sin restricción de empresa
- Los contactos de Empresa A y los de Empresa B son listas separadas, aunque compartan conexión

### Validación de exclusividad — alcance GLOBAL (cross-empresa)

La validación de herramientas exclusivas opera sobre el par `(conexión, contacto)` **sin importar a qué empresa pertenece cada herramienta**.

Antes de guardar/activar una herramienta con `exclusiva = true`, el sistema debe verificar **en toda la DB**:

> Para cada bot_id en `conexiones` y cada contacto resuelto por esta herramienta (incluidos + desconocidos si aplica): ¿existe ya otra herramienta exclusiva activa en **cualquier empresa** que cubra ese mismo par `(bot_id, contacto)`?

Si existe → **error de validación**: mostrar al usuario la herramienta en conflicto y de qué empresa es.

**Lo que SÍ está permitido:**
- Misma conexión en Empresa A con contactos {c1, c2} + misma conexión en Empresa B con contactos {c3, c4} → OK, los pares no se solapan
- Misma conexión en dos empresas, cada una con `incluir_desconocidos = false` y listas de contactos disjuntas → OK

**Lo que NO está permitido:**
- Misma conexión + mismo contacto cubierto por dos herramientas exclusivas, aunque sean de empresas distintas → CONFLICTO

### Ejemplo de configuración — misma empresa

```
Empresa "Acme" — bots: WA-1, WA-2, TG-1

Herramienta A — "Bienvenida VIP"
  tipo: fixed_message
  mensaje: "Hola, te atendemos de inmediato."
  conexiones: [WA-1, WA-2]          ← aplica a ambos WA
  contactos_incluidos: [c1, c2, c3]
  contactos_excluidos: []
  incluir_desconocidos: false
  exclusiva: true ✅

Herramienta B — "Respuesta general"
  tipo: fixed_message
  mensaje: "Gracias por escribir, pronto te respondemos."
  conexiones: []                     ← todas las conexiones de la empresa
  contactos_incluidos: []
  contactos_excluidos: [c1, c2, c3]
  incluir_desconocidos: true
  exclusiva: true ✅

→ Validación OK: c1/c2/c3 → solo A; desconocidos/resto → solo B. Sin conflicto.
```

### Ejemplo de configuración — conexión compartida entre empresas

```
WA-personal (mismo número de teléfono)

Empresa "Acme"
  Herramienta A — "Soporte Acme"
    conexiones: [WA-personal]
    contactos_incluidos: [cliente1, cliente2]   ← contactos de Acme
    incluir_desconocidos: false
    exclusiva: true ✅

Empresa "Beta"
  Herramienta B — "Soporte Beta"
    conexiones: [WA-personal]
    contactos_incluidos: [proveedor1, proveedor2]  ← contactos de Beta
    incluir_desconocidos: false
    exclusiva: true ✅

→ Validación OK: pares (WA-personal, contacto) son disjuntos entre A y B.

❌ Caso inválido:
  Si Beta intenta agregar cliente1 a su herramienta exclusiva
  → ERROR: "WA-personal + cliente1 ya está cubierto por 'Soporte Acme' (Empresa Acme)"
```

### Modelo de datos — tablas adicionales

```sql
CREATE TABLE tools (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  empresa_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK(tipo IN ('fixed_message')),
  config JSON NOT NULL,          -- { "message": "..." } según tipo
  incluir_desconocidos INTEGER NOT NULL DEFAULT 0,
  exclusiva INTEGER NOT NULL DEFAULT 0,
  activa INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tool_connections (
  tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  bot_id TEXT NOT NULL,
  PRIMARY KEY (tool_id, bot_id)
  -- vacío = aplica a todas las conexiones de la empresa
);

CREATE TABLE tool_contacts_included (
  tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  PRIMARY KEY (tool_id, contact_id)
);

CREATE TABLE tool_contacts_excluded (
  tool_id INTEGER NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
  contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  PRIMARY KEY (tool_id, contact_id)
);
```

### UI — gestión de herramientas

Por empresa, sección **Herramientas**:

- Lista de herramientas con nombre, tipo, estado (activa/inactiva), badge "Exclusiva"
- Botón "+ Nueva herramienta" → formulario:
  - Nombre libre
  - Tipo (por ahora solo "Mensaje fijo")
  - Contenido según tipo (textarea para mensaje fijo)
  - Selector de conexiones: checkboxes de los bots de la empresa + opción "Todas"
  - Contactos incluidos: multi-select de la lista de contactos de la empresa
  - Contactos excluidos: multi-select
  - Toggle "Incluir desconocidos"
  - Toggle "Exclusiva"
- Al guardar → validación de exclusividad en tiempo real con feedback claro

---

## Fases de implementación

### Fase 1 — Modelo de datos (DB)

Cambios en `db.js`:
- `createContact(botId, name)`
- `addChannel(contactId, type, value)`
- `getContactsForBot(botId)`
- `findContactByChannel(type, value)` → usado al recibir mensajes

### Fase 2 — API REST

Endpoints nuevos en `api.js`:

```
GET    /api/bots/:botId/contacts          → lista contactos con sus canales
POST   /api/bots/:botId/contacts          → crear contacto { name, channels[] }
PUT    /api/contacts/:id                  → editar nombre
DELETE /api/contacts/:id                  → eliminar contacto + canales
POST   /api/contacts/:id/channels         → agregar canal a contacto
DELETE /api/contact-channels/:id          → quitar canal
```

### Fase 3 — UI Admin

Sección nueva por empresa: **Contactos**
- Lista de contactos con sus canales (WA / TG)
- Botón "+ Agregar contacto" → modal con nombre + canales
- Editar / eliminar contacto
- **Contactos sugeridos**: números que escribieron pero no están en la lista → aparecen como sugerencia con botón "Agregar"

Vinculación con bots:
- Al editar un teléfono/bot, en "Contactos permitidos" se muestra la lista de contactos de la empresa
- Doble clic para agregar/quitar (reemplaza el input de texto actual)

### Fase 4 — Lógica del bot

En `index.js`, al recibir un mensaje:
- Buscar `findContactByChannel('whatsapp', senderPhone)`
- Si existe → es contacto permitido, responder
- Si no existe → ignorar (o registrar como sugerido)

Elimina la dependencia de `allowedContacts` en `phones.json`.

### Fase 5 — Conversaciones unificadas (post-MVP)

- Vista de conversaciones por empresa
- Un hilo = empresa + contacto (sin importar canal)
- Si el mismo contacto escribe por WA y por Telegram, se ve como una sola conversación
- Extiende o reemplaza la tabla `messages` actual

---

## Orden de implementación

### Bloque A — Contactos (base) ✅ completado 2026-03-18
1. ~~Fase 1 — DB: tablas `contacts` + `contact_channels`~~
2. ~~Fase 2 — API REST de contactos~~
3. ~~Fase 3 — UI básica de contactos (con sugeridos)~~
4. ~~Fase 4 — Lógica del bot: reemplazar `allowedContacts` por DB (con fallback JSON)~~

### Bloque B — Herramientas (sobre la base de contactos) ✅ completado 2026-03-18
5. ~~Fase 5 — DB: tablas `tools`, `tool_connections`, `tool_contacts_included/excluded`~~
6. ~~Fase 6 — API REST de herramientas + endpoint de validación de exclusividad~~
7. ~~Fase 7 — UI de herramientas: lista + formulario con multi-select de contactos/conexiones~~
8. ~~Fase 8 — Motor de resolución: reemplazar lógica de respuesta automática por evaluación de herramientas activas~~

### Bloque C — Conversaciones unificadas (post-MVP)
9. Fase 9 — Vista de conversaciones por empresa (sesión aparte)

---

## Dependencias

- Resolver estabilidad del watchdog primero (`ESTADO_WATCHDOG.md`)
- No romper compatibilidad con `phones.json` hasta que la UI de contactos esté operativa
