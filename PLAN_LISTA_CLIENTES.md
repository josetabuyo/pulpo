# Plan: Lista de clientes por empresa

## Objetivo
Reemplazar el `allowedContacts[]` (array de strings en `phones.json`) por una lista de contactos real en la base de datos, con nombre + canales (WA, Telegram, email futuro).

## Por qué
- Hoy los contactos son strings sueltos (nombre o número) en el JSON — frágil y sin estructura
- No hay forma de ver con quién habló cada empresa
- Si el mismo contacto escribe por WA y por Telegram, son registros separados sin relación

---

## Fase 1 — Modelo de datos (DB)

### Tablas nuevas en SQLite

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

### Cambios en `db.js`
- Agregar `createContact(botId, name)`
- Agregar `addChannel(contactId, type, value)`
- Agregar `getContactsForBot(botId)`
- Agregar `findContactByChannel(type, value)` → usado al recibir mensajes

---

## Fase 2 — API REST

Endpoints nuevos en `api.js`:

```
GET    /api/bots/:botId/contacts          → lista contactos con sus canales
POST   /api/bots/:botId/contacts          → crear contacto { name, channels[] }
PUT    /api/contacts/:id                  → editar nombre
DELETE /api/contacts/:id                  → eliminar contacto + canales
POST   /api/contacts/:id/channels         → agregar canal a contacto
DELETE /api/contact-channels/:id          → quitar canal
```

---

## Fase 3 — UI Admin

### Sección nueva por empresa: "Contactos"
- Lista de contactos con sus canales (WA / TG)
- Botón "+ Agregar contacto" → modal con nombre + canales
- Editar / eliminar contacto
- **Contactos sugeridos**: números que escribieron pero no están en la lista → aparecen como sugerencia con botón "Agregar"

### Vinculación con bots
- Al editar un teléfono/bot, en "Contactos permitidos" se muestra la lista de contactos de la empresa
- Click para agregar/quitar (reemplaza el input de texto actual)

---

## Fase 4 — Lógica del bot

En `index.js`, al recibir un mensaje:
- Buscar `findContactByChannel('whatsapp', senderPhone)`
- Si existe → es contacto permitido, responder
- Si no existe → ignorar (o registrar como sugerido)

Elimina la dependencia de `allowedContacts` en `phones.json`.

---

## Fase 5 — Conversaciones unificadas (post-MVP)

- Vista de conversaciones por empresa
- Un hilo = empresa + contacto (sin importar canal)
- Extiende o reemplaza la tabla `messages` actual

---

## Orden de implementación sugerido

1. **Fase 1** — Tablas en DB + funciones en `db.js` (30 min)
2. **Fase 2** — API REST (45 min)
3. **Fase 3** — UI básica sin sugeridos (1h)
4. **Fase 4** — Lógica del bot (30 min)
5. **Fase 5** — Sugeridos + conversaciones (sesión aparte)

---

## Dependencias
- Resolver estabilidad del watchdog primero (`ESTADO_WATCHDOG.md`)
- No romper la compatibilidad con `phones.json` hasta que la UI de contactos esté operativa
