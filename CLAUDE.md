# WhatsApp Bot — Contexto del proyecto

## Forma de trabajar
- Responder siempre en **español**
- Para mensajes cortos: ejecutar `say -v "Paulina" "..."` para hablar en voz alta
- Para código, logs o texto largo: solo texto, sin voz
- Trabajar un problema a la vez

## Worktrees — setup obligatorio al crear uno nuevo
Después de `git worktree add`, siempre crear estos symlinks hacia `_/`:
```bash
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/node_modules  <worktree>/node_modules
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/phones.json   <worktree>/phones.json
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/data          <worktree>/data
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/.wwebjs_auth  <worktree>/.wwebjs_auth
```
Estos archivos son gitignoreados y no se copian solos. Sin ellos el bot no arranca.

## Stack
- Runtime: Node.js
- WhatsApp: `whatsapp-web.js` (no oficial, vía QR)
- Browser: Chrome del sistema (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`)
- DB: SQLite con `better-sqlite3` → `data/messages.db`
- Config: `phones.json` (gitignoreado, datos sensibles)

## Archivos clave
- `index.js` — carga phones.json, crea un Client de WA por cada teléfono
- `db.js` — `logMessage(botId, botPhone, phone, name, body)` y `markAnswered(id)`
- `phones.json` — configuración de bots y teléfonos (GITIGNOREADO, no commitear)
- `phones.example.json` — plantilla sin datos reales (sí commiteable)
- `data/messages.db` — base de datos (auto-creada al arrancar)
- `.wwebjs_auth/` — sesiones WA guardadas, una carpeta por teléfono

## Estructura de phones.json
```
Bot (agrupador lógico)
  ├── id, name, autoReplyMessage (default)
  └── phones[]
        ├── number (sin +, e.g. "5491155612767")
        ├── allowedContacts[] (nombres de contacto en WhatsApp)
        └── autoReplyMessage (opcional, pisa al del bot si está definido)
```

## Decisiones tomadas
- Puppeteer usa Chrome del sistema (no descarga el propio) → `PUPPETEER_SKIP_DOWNLOAD=true` al instalar
- Cada teléfono crea su propia sesión: `LocalAuth({ clientId: "{botId}-{number}" })`
- El mensaje del teléfono tiene prioridad sobre el del bot si está definido
- Si `allowedContacts` de un teléfono está vacío, ese teléfono no responde a nadie
- Ignora mensajes anteriores al inicio del bot (`botReadyTime` por cliente)
- Ignora grupos y mensajes propios

## Tabla messages (SQLite)
| columna   | descripción                        |
|-----------|------------------------------------|
| bot_id    | ID del bot (e.g. "bot_guardia")    |
| bot_phone | Teléfono del bot que recibió       |
| phone     | Teléfono del remitente             |
| name      | Nombre del remitente en WA         |
| body      | Contenido del mensaje              |
| answered  | 0/1                                |

## Comandos frecuentes
```bash
node index.js                      # Arrancar el bot
sqlite3 data/messages.db "SELECT * FROM messages;"   # Ver mensajes
sqlite3 data/messages.db "SELECT bot_phone, phone, name, body, answered FROM messages;"
```

## Importante al arrancar por primera vez tras este cambio
Las sesiones ahora se guardan con un clientId (`{botId}-{number}`), por lo que
**todos los teléfonos deberán re-escanear el QR una vez**. Luego la sesión queda guardada.

## Roadmap
- Fase 1 ✅ MVP: respuesta automática + registro SQLite + multi-teléfono
- Fase 2 🔜 Alertas: si `answered=0` después de X minutos, notificar a contactos de guardia
- Fase 3 📋 Producción: API oficial WhatsApp Business
