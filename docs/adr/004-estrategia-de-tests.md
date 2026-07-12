# ADR-004: Testing en tres capas

**Estado:** Aceptado — en uso desde junio 2026

## Contexto

El sistema tiene lógica de negocio (flows, nodos), un servidor HTTP, y bots
de Telegram reales. Los tests necesitan poder correr rápido en CI (sin bots)
y también verificar el comportamiento real end-to-end antes de un merge.

## Decisión

Tres capas de tests con responsabilidades distintas:

### Capa 1 — Unit tests (inline en `pulpo/`)

Cada módulo de `pulpo/` tiene su propio `test_*.py` al lado del código que testea.

```
pulpo/graphs/nodes/reply/
  __init__.py
  reply.py
  test_reply.py   ← acá
```

- **Sin servidor, sin DB, sin bots** — todo con mocks o funciones puras.
- Corren en < 1 segundo por archivo.
- Se corren con: `uv run pytest pulpo/ -v`

### Capa 2 — Integration tests (`tests/`)

Tests que ejercitan el servidor HTTP completo pero con `ENABLE_BOTS=false`.

```
tests/
  test_auth.py        # login, JWT, contraseña incorrecta
  test_sim.py         # simulador de mensajes
  test_summarizer.py  # API de sumarización
  test_telegram_startup.py  # arranque de bots con mocks
```

- **Requieren servidor corriendo** en `BACKEND_PORT`.
- Corren en segundos, no necesitan Telegram real.
- Se corren con: `BACKEND_PORT=9004 uv run pytest tests/ -v`
- Marcador: `@pytest.mark.integration` para los que requieren servidor.

### Capa 3 — E2E tests (`tests/test_e2e_*.py`, `tests/e2e/**`)

Tests que mandan mensajes reales a bots reales via Telethon y verifican las respuestas.

```
tests/
  test_e2e_luganense_teli.py   # 4 rutas del Orquestador Vendedor (flow viejo, referencia)
  e2e/luganense/
    test_conectividad_telegram.py       # único smoke real por Telegram (marker e2e)
    test_orquestador_vendedor_sim.py    # lógica de negocio, vía simulador (marker e2e_sim)
```

- **Requieren** `ENABLE_BOTS=true`, flows en DB, y sesión `teli user_me` activa.
- Tardan ~2-3 minutos por run (polling de Telegram).
- Se corren **solo antes de un merge a master**, no en CI automático.
- Se corren con: `uv run pytest tests/ -m e2e -v`

### Capa 3b — E2E simulado (`tests/e2e/**`, marker `e2e_sim`)

Tests que ejercitan el motor real de flows (`execute_flow`/`flow_runs`, ADR-006)
a través del simulador in-band `POST /api/flows/{flow_id}/simulate`
(`pulpo/business/flows.py::simulate_flow`, ver `management/HANDOFF_SIMULACION_V2.md`),
sin pasar por Telegram. Los nodos LLM corren reales (misma flakiness de
clasificación que en producción), pero se elimina el settle-time de Telegram
(~180s) y los side-effects externos (`send_message`, `metric`, `save_contact`,
etc.) se saltean vía `state.data["_sim"]`.

- **Requieren** solo el backend local corriendo (`BACKEND_PORT`), no `ENABLE_BOTS`
  ni teli.
- Corren en segundos, no minutos.
- Se corren con: `uv run pytest tests/e2e/ -m e2e_sim -v`
- Es la forma preferida de probar lógica de negocio de un flow de punta a
  punta; el marker `e2e` (Telegram real) queda reservado para un smoke de
  conectividad por bot (ver `test_conectividad_telegram.py` en Luganense).

## Frontend (`frontend/`)

El frontend tiene sus propias dos capas, independientes de las tres de arriba
(esas son todas del backend `pulpo/`):

### Unit tests — lógica pura (`src/**/*.test.js`, vitest)

Para lógica que no depende del DOM ni de xyflow/React (matemática de
posicionamiento, transformaciones de datos, helpers del store que no
requieren un canvas real). Agregado en julio 2026 junto con el snapping a
grilla del editor de flows (`src/utils/grid.js`,
`src/store/flowStore.test.js`) — antes de eso el frontend no tenía forma de
testear lógica pura sin levantar un browser.

```
src/utils/grid.js
src/utils/grid.test.js       ← acá, al lado del código que testea
src/store/flowStore.js
src/store/flowStore.test.js
```

- **Sin browser, sin servidor** — corren en milisegundos.
- Config en `frontend/vitest.config.js`, con `include: ['src/**/*.test.js']`
  para no pisarse con los `.spec.cjs` de Playwright.
- Se corren con: `cd frontend && npm run test:unit`

### E2E / UI tests (`tests/*.spec.cjs`, Playwright)

Tests que levantan un browser real contra el Vite dev server y ejercitan la
UI completa (login, tabs, editor de flows, etc.) — ver `tests/flows.spec.cjs`,
`tests/login.spec.cjs`, etc.

- **Requieren** el frontend (`npm run dev`) y el backend corriendo.
- Se corren con: `cd frontend && npm test` (alias de `npm run test`,
  configurado en `playwright.config.cjs`). Reporta a
  `monitor/test_report_frontend.json`, que alimenta la sección Arquitectura
  del dashboard.

Regla general: si la lógica se puede aislar de React/xyflow, va a
`*.test.js` (vitest, rápido, cero flakiness de drag/DOM). Si depende de
interacción real de usuario en el canvas (arrastrar un nodo con el mouse,
por ejemplo), queda para verificación manual o, si se automatiza, para un
`.spec.cjs` de Playwright — no vale la pena simular drags de xyflow en vitest.

## Cuándo correr qué

| Situación | Qué correr |
|-----------|-----------|
| Cambio en un nodo de flow | `pytest pulpo/graphs/nodes/<nodo>/` |
| PR listo para merge | `pytest pulpo/ tests/ -v` (todo menos e2e) |
| Merge con cambios en flows o Telegram | `pytest tests/ -m e2e -v` + verificar prod |
| Hotfix urgente en prod | Al menos unit tests del módulo tocado |
| Cambio en lógica pura del frontend (store, utils) | `cd frontend && npm run test:unit` |
| Cambio en UI/interacción del editor de flows | `cd frontend && npm run test:unit` + smoke manual del canvas |

## Consecuencias

- **No mockear la DB en integration tests.** Usamos SQLite real (en memoria o archivo temporal).
  Mockear la DB ocultó bugs de migración en el pasado.
- **Los unit tests son la red de seguridad principal.** Si un nodo tiene test, un cambio
  roto falla inmediatamente sin necesitar servidor.
- **E2E tests usan la sesión `user_me` de teli** (`/Users/josetabuyo/Development/teli/data/sessions/user_me.session`).
  Si la sesión expira, `teli user connect` la renueva.
