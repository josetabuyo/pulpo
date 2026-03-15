# Bot Farm — Contexto del proyecto

## Forma de trabajar
- Responder siempre en **español**
- Para mensajes cortos: ejecutar `say -v "Paulina" "..."` para hablar en voz alta
- Para código, logs o texto largo: solo texto, sin voz
- Trabajar un problema a la vez

---

## Rol de Claude en este proyecto

Claude en `_` (master) es el **orquestador y guardián de producción**:

1. **Guardián de prod** — protege el servidor en `_`. Nada se toca en producción sin criterio. Sesiones WA son valiosas: nunca `pkill -9`, nunca borrar perfiles Chrome sin confirmación.

2. **Orquestador** — cuando hay una feature nueva, Claude crea el worktree, hace el setup completo y deja un `NEXT_SESSION.md` con el scope detallado para que otra sesión de Claude arranque sola en ese worktree.

3. **Merges y push** — el merge a master y el push a origin los hace **siempre** la sesión de `_`, nunca un worktree.

4. **Documentos de management** — planes, visión, arquitectura, estados van en `management/`. Son la fuente de verdad para planificar worktrees nuevos.

---

## Forma de trabajo: worktrees como ambientes independientes

Cada feature se desarrolla en su propio worktree, que es un servidor completamente independiente:

- **`_` (master)** → producción real. `ENABLE_BOTS=true`. Bots WA y Telegram reales corriendo.
- **Cualquier otro worktree** → ambiente de desarrollo. `ENABLE_BOTS=false`. Usa **simuladores** para WA y Telegram — no hay browser real, no hay conexiones reales. El pipeline completo (DB, auto_reply, config) funciona igual pero con datos simulados.

Esto permite desarrollar y testear sin arriesgar la sesión de producción ni los bots reales.

### Ciclo de vida de una feature

```
1. Planificar → crear/actualizar doc en management/
2. Crear worktree → git worktree add + setup completo + NEXT_SESSION.md
3. Desarrollar → en la sesión Claude del worktree, modo simulado
4. Mergear → desde la sesión de _, merge + push a origin
5. Eliminar worktree → git worktree remove --force
```

---

## Worktrees — setup obligatorio al crear uno nuevo

### 1. Crear
```bash
git worktree add /Users/josetabuyo/Development/whatsapp_bot/<rama> -b <rama>
```

### 2. Symlinks de archivos gitignoreados
```bash
WDIR=/Users/josetabuyo/Development/whatsapp_bot/<rama>
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/node_modules  $WDIR/node_modules
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/phones.json   $WDIR/phones.json
ln -s /Users/josetabuyo/Development/whatsapp_bot/_/data          $WDIR/data
```

### 3. `.env` con puertos únicos
```
BACKEND_PORT=800X
FRONTEND_PORT=517X
```

### 4. Crear `NEXT_SESSION.md` con el scope completo para el Claude del worktree

### 5. Puertos asignados
| Worktree     | Backend | Frontend | Estado       |
|--------------|---------|----------|--------------|
| `_` (master) | 8000    | 5173     | Producción   |
| dev-1        | 8001    | 5174     | Libre        |
| dev-2        | 8002    | 5175     | Libre        |

---

## Stack actual (Python backend)

- **Backend**: FastAPI + uvicorn (`--reload`)
- **Frontend**: React + Vite
- **DB**: SQLite (`data/messages.db`)
- **Config**: `phones.json` (gitignoreado)
- **WhatsApp**: Playwright headless — `launch_persistent_context`, perfil Chrome en `data/sessions/{number}/profile/`
- **Telegram**: python-telegram-bot, polling

## Archivos clave
- `backend/main.py` — lifespan, routers, CORS
- `backend/state.py` — `clients` dict + `wa_session` singleton
- `backend/automation/whatsapp.py` — lógica WA Web con Playwright
- `backend/api/` — routers: auth, bots, phones, whatsapp, telegram, messages, sim, client
- `backend/sim.py` — motor del simulador (activo cuando `ENABLE_BOTS=false`)
- `frontend/src/pages/DashboardPage.jsx` — dashboard admin
- `frontend/src/pages/ConnectPage.jsx` — portal del cliente
- `phones.json` — configuración de bots y teléfonos (GITIGNOREADO)
- `data/messages.db` — base de datos (auto-creada)
- `data/sessions/` — perfiles Chrome persistentes por sesión WA
- `management/` — documentos de planificación y visión

## Comandos frecuentes
```bash
./start.sh          # levanta back + front (detecta worktree automáticamente)
log_back            # tail en vivo del backend
log_front           # tail en vivo del frontend
```

## Flujo de desarrollo — Tests primero

**El orden siempre es:**
1. Correr los tests existentes antes de tocar código (`pytest tests/ -v` + `playwright test`)
2. Escribir o actualizar tests que cubran la nueva funcionalidad
3. Implementar hasta que los tests pasen
4. Nunca mergear con tests en rojo

Si una feature no tiene tests, escribirlos es parte de la tarea — no opcional.

## Tests

### Backend (pytest + httpx — requiere server corriendo en :8001 o :8000)
```bash
cd backend
pytest tests/ -v
```
Archivos:
- `tests/test_auth.py` — auth, health, mode
- `tests/test_logs.py` — endpoint /api/logs/latest, auth, source inválido
- `tests/test_sim.py`  — simulador: send, log de mensajes, connect/disconnect

### Frontend (Playwright — requiere server corriendo)
```bash
cd frontend
node_modules/.bin/playwright test
```
Archivos:
- `tests/login.spec.cjs`   — login, contraseña incorrecta, dashboard carga
- `tests/monitor.spec.cjs` — botón Monitor, drawer, log live, filtro, pausa, sim→log

> **Nota:** `pytest` y sus dependencias (`pytest-asyncio`, `httpx`) deben estar instalados en el venv:
> ```bash
> .venv/bin/pip install pytest pytest-asyncio httpx
> ```

## Sesiones WhatsApp — reglas críticas
- **NUNCA `pkill -9`** en procesos Playwright/Chromium — SIGKILL corrompe el perfil Chrome y pierde la sesión WA
- Usar solo `pkill` (SIGTERM) para que Chrome guarde limpiamente
- El perfil persiste en disco — al reiniciar siempre intenta restaurar antes de pedir QR nuevo
- Nunca borrar `data/sessions/` sin confirmación explícita del usuario
