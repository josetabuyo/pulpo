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
                  #   transcription, browser
frontend/         # React + Vite (dev: :5173, prod: dist/ compilado)
tests/            # integration tests + e2e tests (ver ADR-004)
scripts/          # scripts operacionales standalone (expirar conversaciones, migraciones ad-hoc)
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
telegram), transcripción, browser. Los nodos importan directamente de `tools/`.
Nadie más. `business/` solo recibe FlowState — sin conocimiento de canal.
Consultas HTTP genéricas a APIs externas (Luganense incluida) no necesitan un
módulo dedicado en `tools/` — se resuelven con `FetchHttpNode` configurado
directo en el editor de flows (ver ADR-011).

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
| [007](docs/adr/007-diagramas-arquitectura.md) | Diagramas de arquitectura, dominio conexiones separado, fetch dividido en fetch_http/fetch_fb — el split original está superado por 011 |
| [008](docs/adr/008-noticias-dominio-luganense.md) | Tabla de noticias pasa a ser dominio de Luganense (vía HTTP, no más SQLite local) — superado por 009 |
| [009](docs/adr/009-scraping-dominio-fabi.md) | El scraping de Facebook en sí (no solo la cache) pasa a ser dominio de Fabi, servicio propio — parcialmente superado por 011 |
| [010](docs/adr/010-noticias-http-directo-a-luganense.md) | Pulpo consulta `/api/noticias` de Luganense directo por HTTP GET, sin dependencia en tiempo de ejecución de Fabi — superado del todo por 011 |
| [011](docs/adr/011-fetch-fb-eliminado-todo-via-fetch-http.md) | Se elimina `FetchFbNode` — todo consumo de APIs externas (Luganense incluida) es `FetchHttpNode` genérico configurado en el editor |

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

**Facebook — no es parte de Pulpo, ni en código ni en el editor de flows (ver
ADR-011).** Pulpo no scrapea Facebook, no maneja cookies de FB, no importa
ningún módulo de `fabi`, y no tiene ningún nodo dedicado a Facebook. El
scraping y la inyección a Luganense viven enteros en
`/Users/josetabuyo/Development/Fabi` (proyecto propio, agente LAS, patrón
`wavi`), corriendo por su cuenta — Pulpo no lo dispara ni lo sabe. Cookies de
FB, login, renovación: `fabi login <page_id>` / `fabi status` desde el repo
de Fabi, no acá.

Para consumir noticias del barrio, el flow de Luganense usa un `FetchHttpNode`
genérico apuntando a `GET /api/noticias?page_id=&q={query}` — mismo patrón que
`/api/directorio/buscar` para comercios/servicios. Sin límite de resultados
todavía (el endpoint no pagina); si hace falta un flow conversacional de
noticias ("traer de a 3", "contame más"), coordinar con Luganense (agente LAS
propio) para agregar `limit`/`offset` al contrato — spec por escrito, esperar
confirmación antes de integrar (mismo criterio que ADR-008).

---

## Producción

- **Backend:** `http://localhost:8000` — `pulpo server ui`, bots WA y TG activos
- **Frontend dev:** `http://localhost:5173` — Vite, proxy `/api` → 8000
- **Proceso:** PID administrado por launchd (`com.josetabuyo.pulpo`)
- **Venv:** `.venv-pulpo/` editable sobre `_/` — no requiere reinstalar al cambiar código
- **Config:** `_/.env` (gitignoreado) — `ADMIN_PASSWORD`, `BACKEND_PORT`, `ENABLE_BOTS=true`

---

## Flujo para una feature nueva

Los cambios chicos se hacen directo en `master`. Para un cambio grande, worktree
por tarea (ADR-003):

```
1. Crear worktree  →  git worktree add ../pulpo/<rama> -b <rama>
2. Setup symlinks  →  ver ADR-003
3. Desarrollar     →  ENABLE_BOTS=false, puerto distinto al 8000
4. Tests           →  uv run pytest pulpo/ tests/ -v
5. Si toca flows   →  uv run pytest tests/ -m e2e -v (bots reales, antes del merge)
6. Merge           →  desde _ : git merge <rama> --no-ff && git push origin master
7. Limpiar         →  stop-backend en worktree → git worktree remove <rama>
```

**Sin simulador.** El simulador viejo (`business/sim.py`, `/sim/*`, `pulpo sim`,
`SimChat.jsx`) se borró — no se usa más, ni en worktrees ni en master. Para probar
un flow, e2e con bots reales de Telegram (ver "Tests" abajo) hasta tener el
sistema de simulación in-band diseñado en `management/HANDOFF_SIMULACION_V2.md`.

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

2. **Orquestador** — para cambios grandes, crea worktrees con setup completo y documenta el scope en `management/`.

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

# Frontend — unit tests de lógica pura (vitest, sin browser)
cd frontend && npm run test:unit

# Frontend — e2e/UI (Playwright, requiere front + back corriendo)
cd frontend && npm test
```

Ver [ADR-004](docs/adr/004-estrategia-de-tests.md) para el detalle de cuándo
usar cada capa (backend tiene tres, frontend tiene dos).

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
| `pulpo/graphs/compiler.py` | Motor de flows: `execute_flow()` (un flow) y `dispatch_message()` (todos los flows de una bot para un mensaje entrante) |
| `pulpo/graphs/conversation.py` | Dueño de cuándo un flow acumula `data["conversation"]` (triggers de canal humano, wait_user) |
| `pulpo/business/flows.py` | CRUD de flows + `trigger_flow()` (entrada vía api_trigger) |
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
