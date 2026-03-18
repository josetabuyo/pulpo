# Plan: Portal de empresa — ✅ COMPLETADO

## Estado

**Completado y en producción** (2026-03-18).

Todas las fases implementadas. El portal es funcional y autogestionable.

---

## Lo que se construyó

| Componente | Descripción |
|---|---|
| `POST /empresa/auth` | Login por contraseña, identifica la empresa y devuelve `bot_id` |
| `GET /empresa/{bot_id}` | Info + lista de conexiones con estado |
| `POST /empresa/{bot_id}/whatsapp` | Agregar número WA, inicia sesión |
| `POST /empresa/{bot_id}/telegram` | Agregar bot TG por token |
| `DELETE /empresa/{bot_id}/whatsapp/{id}` | Eliminar conexión WA |
| `DELETE /empresa/{bot_id}/telegram/{id}` | Eliminar bot TG |
| `PUT /empresa/{bot_id}/tools` | Guardar mensaje de respuesta automática |
| `GET /empresa/{bot_id}/messages/{number}` | Lista de conversaciones por canal |
| `GET /empresa/{bot_id}/chat/{number}/{contact}` | Historial de un contacto |
| `POST /empresa/{bot_id}/chat/{number}/{contact}` | Enviar mensaje (WA o Telegram) |
| `POST /empresa/nueva` | Alta de empresa nueva (sin auth) |
| `EmpresaPage.jsx` | Portal completo: login, dashboard, chat inline, gestión de conexiones |
| `NuevaEmpresaPage.jsx` | Onboarding: datos → conexiones → listo |

## Flujo implementado

1. Empresa entra a `/empresa` con su contraseña
2. Ve dashboard con: respuesta automática, canales WA/TG con estado y conversaciones
3. Puede agregar/eliminar conexiones WA y TG desde el mismo portal
4. Puede chatear con cada contacto inline
5. Alta de empresa nueva en `/empresa/nueva` (link en blanco, sin contraseña)

## Notas

- El chat de Telegram enviaba mensajes por `wa_session` — bug corregido el 2026-03-18
- `ConfigView` fue absorbida por `EmpresaDashboard` — ya no existe como componente separado
- `allowedContacts` de Telegram no se filtra en el portal (se ve todo el historial)
