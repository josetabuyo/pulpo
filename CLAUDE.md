# Pulpo — Contexto del proyecto

## Forma de trabajar
- Responder siempre en **español**
- Para mensajes cortos, hablar via la cola del backend:
  ```bash
  curl -s -X POST http://localhost:8700/queue/speak \
    -H "Content-Type: application/json" \
    -d '{"text":"...","voice":"Tessa","family":"Pulpo"}'
  ```
- Para código, logs o texto largo: solo texto, sin voz
- Trabajar un problema a la vez

---

## Arquitectura actual

El backend es el paquete pip `pulpo` instalado en modo editable desde `_/`.
No existe `backend/` — fue eliminado. Ver `docs/adr/001-paquete-pulpo.md`.

```
pulpo/
  business/       # lógica de dominio: flows, contactos, sim, wavi, bots,
                  #   connections_phones (WhatsApp/connections.json),
                  #   connections_google (Google service accounts/DB)
  core/           # db, config, state, lifespan
  graphs/         # compilador de flows + nodos (uno por archivo en graphs/nodes/)
  interfaces/
    api/          # FastAPI puro — routers bajo /api
    ui/           # API + SPA estática — entrypoint de producción
    cli/          # CLI Click: pulpo server ui|api, pulpo db init
    lib/          # PulpoClient — Python API in-process
  bots/           # driver de Telegram (telegram_bot.py, python-telegram-bot)
  tools/          # todo lo externo que un nodo puede usar: wavi_driver (WhatsApp),
                  #   facebook/ (scraping), transcription, browser
frontend/         # React + Vite (dev: :5173, prod: dist/ compilado)
tests/            # integration tests + e2e tests (ver ADR-004)
scripts/          # scripts operacionales standalone (ver "Renovar cookies de FB" abajo)
docs/adr/         # decisiones de arquitectura
```

> No existe `pulpo/connections/` como paquete — es un nombre de dominio, no un
> directorio. Los drivers de canal reales viven en `tools/` (WhatsApp vía wavi_driver)
> y en `bots/` (Telegram). Si en algún momento se justifica unificarlos bajo un
> paquete propio, actualizar este documento en el mismo commit que el movimiento.

**Regla de oro:** la lógica va en `pulpo/business/` o `pulpo/graphs/`.
Las interfaces solo coordinan. Los tests unitarios van inline junto al código
que testean (`pulpo/graphs/nodes/test_router.py`, `pulpo/business/test_flows.py`).

**`tools/` es todo lo externo que un nodo puede usar** — drivers de canal (wavi,
telegram), scraping de Facebook, transcripción, browser. Los nodos importan
directamente de `tools/`. Nadie más. `business/` solo recibe FlowState — sin
conocimiento de canal.

**Cada ejecución de flow tiene un `run_id`** (ADR-006). El compilador loguea cada step
en `flow_run_steps` con el FlowState de entrada y salida. Permite debug visual y gates
bloqueantes (flows que esperan un evento externo para reanudar).

---

## ADRs — leer antes de cambiar algo

| ADR | Tema |
|-----|------|
| [001](docs/adr/001-paquete-pulpo.md) | Por qué `pulpo/` reemplazó `backend/` |
| [002](docs/adr/002-cuatro-interfaces.md) | Las 4 interfaces y cuándo agregar a cada una |
| [003](docs/adr/003-worktrees-y-flujo-de-features.md) | Features en worktrees, merge desde master |
| [004](docs/adr/004-estrategia-de-tests.md) | Unit / integration / e2e — cuándo correr qué |
| [005](docs/adr/005-produccion-launchd.md) | Launchd, `.venv-pulpo`, comandos de prod |
| [006](docs/adr/006-durable-workflow-journal.md) | Flow runs con journal en DB — debug visual y gates bloqueantes |

---

## Scripts de operación

Todos se corren desde la raíz de `_/`. **Nunca usar uvicorn directo ni matar procesos a mano.**

```bash
./start.sh            # levanta back + front
./start.sh back       # solo backend
./start.sh front      # solo frontend (Vite dev)
./stop-backend.sh     # detiene backend con SIGTERM (seguro para WhatsApp)
./stop-frontend.sh    # detiene el Vite dev server con SIGTERM
./restart-backend.sh  # stop + sleep 3 + start back
```

**Cookies de Facebook (Luganense scrapea FB para noticias del barrio):**

```bash
python scripts/fb_login.py          # renovar cookies — abre browser visible, resolver 2FA/captcha a mano
python scripts/fb_check_cookies.py  # chequear expiración — alerta por Telegram al admin si hay problema
python scripts/test_fb_debug.py     # smoke-test manual del scraping + cache (no es pytest)
```

`fb_check_cookies.py` está pensado para correr por cron diario (ver docstring del script).

---

## Producción

- **Backend:** `http://localhost:8000` — `pulpo server ui`, bots WA y TG activos
- **Frontend dev:** `http://localhost:5173` — Vite, proxy `/api` → 8000
- **Proceso:** PID administrado por launchd (`com.josetabuyo.pulpo`)
- **Venv:** `.venv-pulpo/` editable sobre `_/` — no requiere reinstalar al cambiar código
- **Config:** `_/.env` (gitignoreado) — `ADMIN_PASSWORD`, `BACKEND_PORT`, `ENABLE_BOTS=true`

---

## Flujo para una feature nueva

```
1. Crear worktree  →  git worktree add ../pulpo/<rama> -b <rama>
2. Setup symlinks  →  ver ADR-003
3. Desarrollar     →  ENABLE_BOTS=false (simulador), puerto distinto al 8000
4. Tests           →  uv run pytest pulpo/ tests/ -v
5. Si toca flows   →  uv run pytest tests/ -m e2e -v (bots reales, antes del merge)
6. Merge           →  desde _ : git merge <rama> --no-ff && git push origin master
7. Limpiar         →  stop-backend en worktree → git worktree remove <rama>
```

---

## Multi-agente — Haiku y Opus

Al inicio de cada respuesta, chequeá silenciosamente flags pendientes:
```bash
ls session/haiku-done.flag session/opus-done.flag 2>/dev/null
```

- **Haiku** → lectura masiva, búsquedas, análisis de logs → `session/haiku-inbox.md`
- **Opus** → arquitectura, merges riesgosos, decisiones de impacto → `session/opus-inbox.md`

---

## Rol de Claude en este proyecto

Claude en `_` (master) es el **orquestador y guardián de producción**:

1. **Guardián de prod** — nada se toca en producción sin criterio. Sesiones WA son valiosas:
   nunca `pkill -9` en Chromium, nunca borrar `data/sessions/` sin confirmación.

2. **Orquestador** — crea worktrees con setup completo y documenta el scope en `management/`.

3. **Merges y push** — siempre desde `_/`, nunca desde un worktree.

---

## Tests — referencia rápida

```bash
# Unit tests (sin servidor)
uv run pytest pulpo/ -v

# Integration tests (requiere servidor en BACKEND_PORT)
BACKEND_PORT=8000 ADMIN_PASSWORD=... uv run pytest tests/ -v

# E2E tests (requiere ENABLE_BOTS=true + teli user_me activo)
uv run pytest tests/ -m e2e -v

# Todo junto
BACKEND_PORT=8000 ADMIN_PASSWORD=... uv run pytest pulpo/ tests/ -v
```

---

## Archivos clave

| Archivo | Descripción |
|---------|-------------|
| `pulpo/interfaces/api/app.py` | FastAPI app, registra los 17 routers |
| `pulpo/interfaces/ui/app.py` | App de producción (API + SPA) |
| `pulpo/interfaces/cli/main.py` | Entrypoint CLI |
| `pulpo/core/lifespan.py` | Startup: DB, bots Telegram, wavi poller |
| `pulpo/core/db.py` | SQLite async (aiosqlite) |
| `pulpo/core/config.py` | Lee `connections.json` |
| `pulpo/graphs/compiler.py` | Compila y ejecuta flows |
| `pulpo/business/flows.py` | CRUD de flows + `run_flows()` |
| `connections.json` | Config de bots y conexiones (gitignoreado) |
| `data/messages.db` | Base de datos (gitignoreado, auto-creada) |
| `start-backend-launchd.sh` | Script de arranque para launchd |
| `com.josetabuyo.pulpo.plist` | Plist de launchd |

---

## Browsers automatizados — tres tipos distintos

| Tipo | Cómo identificarlo | Tocar |
|------|--------------------|-------|
| `playwright-cli` (Claude) | CLI efímero, sin user-data-dir persistente | ✅ OK cerrar |
| Bots WA | `--user-data-dir=.../data/sessions/{número}/profile` | ❌ NUNCA |
| Tests de UI | Chrome lanzado por `playwright test` | ✅ OK |
