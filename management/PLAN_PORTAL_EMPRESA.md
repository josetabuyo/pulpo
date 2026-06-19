# Plan: Portal de bot — ✅ COMPLETADO

## Estado

**Completado y en producción** (2026-03-18).

Todas las fases implementadas. El portal es funcional y autogestionable.

---

## Lo que se construyó

| Componente | Descripción |
|---|---|
| `POST /bot/auth` | Login por contraseña, identifica la bot y devuelve `bot_id` |
| `GET /bot/{bot_id}` | Info + lista de conexiones con estado |
| `POST /bot/{bot_id}/whatsapp` | Agregar número WA, inicia sesión |
| `POST /bot/{bot_id}/telegram` | Agregar bot TG por token |
| `DELETE /bot/{bot_id}/whatsapp/{id}` | Eliminar conexión WA |
| `DELETE /bot/{bot_id}/telegram/{id}` | Eliminar bot TG |
| `PUT /bot/{bot_id}/tools` | Guardar mensaje de respuesta automática |
| `GET /bot/{bot_id}/messages/{number}` | Lista de conversaciones por canal |
| `GET /bot/{bot_id}/chat/{number}/{contact}` | Historial de un contacto |
| `POST /bot/{bot_id}/chat/{number}/{contact}` | Enviar mensaje (WA o Telegram) |
| `POST /bot/nueva` | Alta de bot nueva (sin auth) |
| `BotPage.jsx` | Portal completo: login, dashboard, chat inline, gestión de conexiones |
| `NewBotPage.jsx` | Onboarding: datos → conexiones → listo |

## Flujo implementado

1. Bot entra a `/bot` con su contraseña
2. Ve dashboard con: respuesta automática, canales WA/TG con estado y conversaciones
3. Puede agregar/eliminar conexiones WA y TG desde el mismo portal
4. Puede chatear con cada contacto inline
5. Alta de bot nueva en `/bot/nueva` (link en blanco, sin contraseña)

## Notas

- El chat de Telegram enviaba mensajes por `wa_session` — bug corregido el 2026-03-18
- `ConfigView` fue absorbida por `BotDashboard` — ya no existe como componente separado
- `allowedContacts` de Telegram no se filtra en el portal (se ve todo el historial)
