# WhatsApp Bot — Contexto del proyecto

## Forma de trabajar
- Responder siempre en **español**
- Para mensajes cortos: ejecutar `say -v "Paulina" "..."` para hablar en voz alta
- Para código, logs o texto largo: solo texto, sin voz
- Trabajar un problema a la vez

## Worktrees — setup obligatorio al crear uno nuevo

Cada worktree es un ambiente **completamente independiente** con su propio back y front.
**NUNCA compartir puertos entre worktrees.** Cada ambiente tiene los suyos.

### 1. Crear el worktree
```bash
git worktree add /Users/josetabuyo/Development/whatsapp_bot/<nombre-rama> <nombre-rama>
```

### 2. Symlinks de archivos gitignoreados (obligatorio)
```bash
WDIR=/Users/josetabuyo/Development/whatsapp_bot/<nombre-rama>
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/node_modules  $WDIR/node_modules
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/phones.json   $WDIR/phones.json
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/data          $WDIR/data
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/.wwebjs_auth  $WDIR/.wwebjs_auth
```

### 3. Crear el .env con puertos únicos para este ambiente
```bash
cp /Users/josetabuyo/Development/whatsapp_bot/_/.env.example $WDIR/.env
# Editar $WDIR/.env con puertos que no estén en uso:
#   master (estable): BACKEND_PORT=8000  FRONTEND_PORT=5173
#   dev-1:            BACKEND_PORT=8001  FRONTEND_PORT=5174
#   dev-2:            BACKEND_PORT=8002  FRONTEND_PORT=5175
```

### 4. Arrancar el ambiente
```bash
cd $WDIR && ./start.sh          # back + front juntos
cd $WDIR && ./start.sh back     # solo backend
cd $WDIR && ./start.sh front    # solo frontend
```

El script `start.sh` imprime al arrancar:
```
════════════════════════════════════════
  Ambiente : <nombre-rama>
  Backend  : http://localhost:8001
  Frontend : http://localhost:5174
════════════════════════════════════════
```

### Tabla de ambientes activos (actualizar al crear/borrar)
| Worktree / Rama  | Backend            | Frontend           | Propósito          |
|------------------|--------------------|--------------------|--------------------|
| `_` (master)     | :8000              | :5173              | Estable / producción |
| (libre)          | :8001              | :5174              | Dev 1              |
| (libre)          | :8002              | :5175              | Dev 2              |

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
