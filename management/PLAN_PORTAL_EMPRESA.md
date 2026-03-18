# Plan: Portal de empresa (evolución de /connect)

## Qué es hoy

`/connect` es un portal para un bot específico: la empresa ingresa una contraseña,
luego tipea manualmente un número de teléfono, y llega al portal de *ese* número.

Problemas:
- La empresa tiene que saber su número de teléfono de antemano
- No puede ver todos sus canales juntos
- No puede agregar una nueva conexión sola
- No hay concepto de "empresa" — solo hay "número"

---

## Qué queremos

Una empresa recibe el link `/empresa` (o `/connect`, se puede renombrar después).
Entra con su contraseña. Ve **su empresa**: todos los canales conectados, puede
agregar uno nuevo, puede configurar sus herramientas. Se autogestiona.

---

## Flujo de usuario nuevo

```
1. La empresa entra a /empresa
2. Ingresa su contraseña → el backend la identifica como "GM Herrería" (por ej.)
3. Ve el dashboard de su empresa:
   - Lista de conexiones activas (WA, Telegram)
   - Herramientas configuradas (mensaje de auto-reply por ahora)
   - Botón "Agregar conexión"
4. Si agrega una conexión WA:
   - NO pide número de teléfono
   - Muestra QR directamente
   - Cuando escanea → WA Web devuelve el número → se crea la conexión automáticamente
5. Si agrega Telegram: campo para el token del bot (futuro)
```

---

## Cambios en el backend

### Auth de empresa
Hoy `require_client` verifica `CLIENT_PASSWORD` (una sola contraseña global).
Necesitamos que la contraseña identifique a una empresa específica.

**Opción elegida:** cada bot en `phones.json` ya tiene un campo de contraseña.
El endpoint de login busca qué bot corresponde a esa contraseña y devuelve el `bot_id`.

```
POST /empresa/auth   { password }
→ { ok: true, bot_id: "gm_herreria", bot_name: "GM Herrería y Electricidad" }
```

El `bot_id` se guarda en sessionStorage y se manda en cada request siguiente.

### Endpoints nuevos

```
GET  /empresa/{bot_id}                → info de la empresa + lista de conexiones
POST /empresa/{bot_id}/whatsapp       → iniciar nueva sesión WA (sin teléfono)
GET  /empresa/{bot_id}/whatsapp/{id}/qr → QR de la sesión nueva
GET  /empresa/{bot_id}/whatsapp/{id}/status → estado (waiting_qr / authenticated / ready)
DELETE /empresa/{bot_id}/whatsapp/{id} → eliminar conexión
PUT  /empresa/{bot_id}/tools          → guardar configuración de herramientas (auto-reply, etc.)
```

### Agregar WA sin teléfono
Hoy la sesión se indexa por número de teléfono. Para crear una sesión nueva sin
conocer el número:
1. Backend genera un `session_id` temporal (UUID corto)
2. Lanza el browser con ese ID, navega a WA Web, espera QR
3. Cuando el usuario escanea, WA Web muestra el número del celular en el DOM
4. El backend detecta el número, renombra la sesión, lo guarda en `phones.json`

Esto ya existe parcialmente — `whatsapp.py` tiene lógica de `wait_for_auth()`.
Solo falta extraer el número del DOM después de autenticar.

---

## Cambios en el frontend

### Nueva página: `EmpresaPage.jsx`
Reemplaza o convive con `ConnectPage.jsx`. Ruta: `/empresa`.

**Componentes:**
- `EmpresaLogin` — pantalla de login (solo contraseña, sin teléfono)
- `EmpresaDashboard` — dashboard principal de la empresa
  - `ConexionesList` — lista de WA/Telegram con badge de estado
  - `ConexionCard` — card por canal: estado, conectar/desconectar, QR inline
  - `HerramientasPanel` — configuración de tools (auto-reply hoy, más después)
  - `AgregarConexionModal` — modal para iniciar nueva conexión WA o Telegram

### Lo que se reutiliza de `ConnectPage.jsx`
- `StatusBadge` — sin cambios
- La lógica del QR inline (`connectAndPoll`) — se reutiliza por conexión
- `ContactChat` + conversaciones — se mueve dentro de `ConexionCard`

---

## Herramientas (tools) — modelo extensible

Las herramientas se configuran por empresa (aplican a todas las conexiones)
o por conexión (override por canal). Hoy hay una sola:

| Tool | Descripción | Aplica a |
|------|-------------|----------|
| `auto_reply` | Mensaje fijo cuando llega un mensaje | WA y Telegram |

En el futuro:
| Tool | Descripción |
|------|-------------|
| `ai_agent` | Respuesta generada por IA con contexto de la empresa |
| `menu` | Menú de opciones que ramifica según respuesta |
| `alert_no_response` | Alerta si un mensaje no fue respondido en X minutos |

La UI de herramientas es una lista de cards ON/OFF con configuración expandible.
Hoy solo se muestra `auto_reply` — las demás se muestran cuando estén disponibles.

---

## Modelo de datos — qué cambia en phones.json

Hoy:
```json
{
  "bots": [{
    "id": "gm_herreria",
    "name": "GM Herrería y Electricidad",
    "password": "...",
    "autoReplyMessage": "...",
    "phones": [{ "number": "5491155612767" }],
    "telegram": [{ "token": "..." }]
  }]
}
```

No cambia la estructura — solo se usa de forma diferente:
- El login busca por `password` → devuelve `bot_id`
- La empresa ve todas sus `phones` y `telegram` como conexiones

---

## Fases de implementación

### Fase 1 — Auth de empresa + dashboard básico
- Endpoint `POST /empresa/auth` que identifica empresa por contraseña
- `GET /empresa/{bot_id}` que devuelve conexiones + estado
- Frontend: `EmpresaPage` con login y lista de conexiones (solo lectura + conectar/desconectar)
- Sin agregar nuevas conexiones aún

### Fase 2 — Agregar conexión WA (sin teléfono)
- Backend: detectar número del DOM tras escanear QR
- Backend: guardar nueva conexión en `phones.json`
- Frontend: botón "Agregar WhatsApp" → QR → conexión creada automáticamente

### Fase 3 — Herramientas
- UI de tools con auto-reply configurable por empresa
- Override por conexión (mensaje distinto por número)

### Fase 4 — Telegram
- Agregar conexión Telegram: campo para token del bot
- Misma UI de tools que WA

---

## Lo que NO cambia
- La ruta `/connect` puede seguir existiendo por compatibilidad (o redirigir a `/empresa`)
- La UI de admin (`/dashboard`) sigue igual — es para el dueño de la plataforma, no para las empresas
- `phones.json` sigue siendo la fuente de verdad (hasta que tengamos DB de empresas)

---

## Dependencias
- Ninguna bloqueante — se puede empezar desde Fase 1 ya

## Estado
Pendiente — worktree no creado
