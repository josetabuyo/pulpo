# Pulpo — Contexto del proyecto

## Forma de trabajar
- Responder siempre en **español**
- Para mensajes cortos: ejecutar `say -v "Paulina" "..."` para hablar en voz alta
- Para código, logs o texto largo: solo texto, sin voz
- Trabajar un problema a la vez

## Comandos Bash — siempre simples y auditables

**Regla obligatoria:** cada llamada al Bash tool debe hacer **una sola cosa**.

- ✅ `grep "full-sync" backend.log`
- ✅ `tail -20 backend.log`
- ✅ `curl -s http://localhost:8000/health`
- ❌ `grep X | awk | xargs rm` — demasiado en un solo comando
- ❌ `kill $(ps aux | grep ... | awk ...)` — encadenar kill con subshell es peligroso

**Por qué:** el usuario puede aprobar/rechazar cada comando individualmente.
Si un comando hace A+B+C en un pipe, no puede aprobar A sin B.
Comandos simples = auditoría real.

**Cuando necesites encadenar:** pedir aprobación explícita o dividir en pasos separados.

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
git worktree add /Users/josetabuyo/Development/pulpo/<rama> -b <rama>
```

### 2. Symlinks de archivos gitignoreados
```bash
WDIR=/Users/josetabuyo/Development/pulpo/<rama>
ln -s /Users/josetabuyo/Development/pulpo/_/node_modules  $WDIR/node_modules
ln -s /Users/josetabuyo/Development/pulpo/_/phones.json   $WDIR/phones.json
# ⚠️  NO linkear data/ — cada worktree tiene su propia data/ aislada
# El backend la crea automáticamente al arrancar (messages.db vacía, sin sesiones WA reales)
mkdir -p $WDIR/data
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

- **Backend**: FastAPI + uvicorn (sin `--reload` en producción, con `--reload` en worktrees dev)
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

## Scripts y aliases — la única forma correcta de operar el servidor

Todos se corren parados en la raíz del worktree (`_/` para producción).
**Nunca usar comandos manuales de uvicorn ni matar procesos a mano.**

### Scripts (en disco, ya aprobados)
```bash
./start.sh            # levanta back + front
./start.sh back       # solo backend (si ya corre, no lo reinicia)
./start.sh front      # solo frontend
./stop-backend.sh     # detiene el backend con SIGTERM (seguro para WA)
./restart-backend.sh  # stop + sleep 3 + start back (safe: WA reconnecta sola)
```

### Aliases en ~/.zshrc (correr desde la raíz del worktree)
```bash
start       # alias de ./start.sh
log_back    # tail -f ./monitor/backend.log
log_front   # tail -f ./monitor/frontend.log
qdb "SQL"   # query directo sobre data/messages.db de producción
```

### ⚠️ Regla de logs
`log_back` solo muestra logs cuando el servidor fue iniciado vía `./start.sh`
(que redirige stdout a `monitor/backend.log`).
Si el servidor se inició a mano en una terminal, los logs van a esa terminal — no al archivo.
**Siempre arrancar con `./start.sh` para que `log_back` funcione.**

## Flujo de desarrollo — Tests primero

**El orden obligatorio, siempre:**
1. Correr los tests existentes antes de tocar código (`pytest tests/ -v` + `playwright test`)
2. Leer el output — los errores describen qué asume el sistema, valen más que leer código en frío
3. Implementar hasta que los tests pasen
4. Nunca mergear con tests en rojo

**Tests nuevos:**
- Lo ideal es seguir TDD: escribir el test antes de implementar
- Si agregar tests nuevos cuesta más que el cambio (layouts, prototipos, exploración), se pueden omitir en el medio y escribir al terminar el feature
- Si el cambio rompe un test existente de forma intencional (UI que cambió), actualizarlo es parte del trabajo

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

## Browsers automatizados — tres usos distintos

Hay tres tipos de browser Playwright/Chromium corriendo en paralelo. **Nunca confundirlos:**

| Tipo | Cómo identificarlo en `ps` | Tocar |
|------|---------------------------|-------|
| **MCP** (Claude + dev) | proceso node `playwright-mcp` + Chrome con `--user-data-dir=/var/folders/...` | ✅ OK matar |
| **WA bots** | Chrome con `--user-data-dir=.../data/sessions/{número}/profile` | ❌ NUNCA |
| **Tests de UI** | Chrome lanzado por `playwright test` (también `/var/folders/...`) | ✅ OK (solo existen mientras corren tests) |

### Cuando el MCP se traba
El servidor MCP es el proceso node `playwright-mcp` — **nunca matarlo**, es el que le da las herramientas de browser a Claude.

Lo que hay que hacer es matar solo el **Chrome** que el MCP lanzó (tiene user-data-dir temporal en `/var/folders/...`). El servidor node lo reinicia solo:

```bash
# Matar solo el Chrome del MCP (NO el servidor node)
pkill -f "playwright_chromiumdev_profile"

# Verificar que los WA bots sobrevivieron
ps aux | grep "data/sessions" | grep -v grep
```

Si el servidor node también está caído (porque alguien lo mató), el **usuario** lo reinicia en su terminal:
```bash
npm exec @playwright/mcp@latest --browser chromium
```
Claude NO puede iniciarlo — necesita que el servidor esté corriendo para tener las herramientas.

La clave para distinguir: `--user-data-dir`
- `/var/folders/...` → temporal (MCP o test) — matar el Chrome OK, nunca el node server
- `.../data/sessions/` → persistente WA — NUNCA tocar

## Sesiones WhatsApp — reglas críticas
- **NUNCA `pkill -9`** en procesos Playwright/Chromium — SIGKILL corrompe el perfil Chrome y pierde la sesión WA
- Usar solo `pkill` (SIGTERM) para que Chrome guarde limpiamente
- El perfil persiste en disco — al reiniciar siempre intenta restaurar antes de pedir QR nuevo
- Nunca borrar `data/sessions/` sin confirmación explícita del usuario
