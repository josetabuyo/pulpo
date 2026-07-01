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

### Capa 3 — E2E tests (`tests/test_e2e_*.py`)

Tests que mandan mensajes reales a bots reales via Telethon y verifican las respuestas.

```
tests/
  test_e2e_luganense_teli.py   # 4 rutas del Orquestador Vendedor
```

- **Requieren** `ENABLE_BOTS=true`, flows en DB, y sesión `teli user_me` activa.
- Tardan ~2-3 minutos por run (polling de Telegram).
- Se corren **solo antes de un merge a master**, no en CI automático.
- Se corren con: `uv run pytest tests/ -m e2e -v`

## Cuándo correr qué

| Situación | Qué correr |
|-----------|-----------|
| Cambio en un nodo de flow | `pytest pulpo/graphs/nodes/<nodo>/` |
| PR listo para merge | `pytest pulpo/ tests/ -v` (todo menos e2e) |
| Merge con cambios en flows o Telegram | `pytest tests/ -m e2e -v` + verificar prod |
| Hotfix urgente en prod | Al menos unit tests del módulo tocado |

## Consecuencias

- **No mockear la DB en integration tests.** Usamos SQLite real (en memoria o archivo temporal).
  Mockear la DB ocultó bugs de migración en el pasado.
- **Los unit tests son la red de seguridad principal.** Si un nodo tiene test, un cambio
  roto falla inmediatamente sin necesitar servidor.
- **E2E tests usan la sesión `user_me` de teli** (`/Users/josetabuyo/Development/teli/data/sessions/user_me.session`).
  Si la sesión expira, `teli user connect` la renueva.
