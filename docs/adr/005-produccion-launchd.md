# ADR-005: Producción via launchd con instalación editable

**Estado:** Aceptado — en producción desde 2026-06-29

## Contexto

El servidor de producción necesita arrancar automáticamente al boot, sobrevivir
reinicios, y usar siempre el código de master sin pasos de build explícitos.

## Decisión

Producción usa **launchd** (macOS) con un plist que ejecuta `start-backend-launchd.sh`.

### Componentes

**`com.josetabuyo.pulpo.plist`** — registrado en `~/Library/LaunchAgents/`.
Configura `KeepAlive: true` para que launchd reinicie el proceso si muere.

**`start-backend-launchd.sh`** — sourcea `.env` y ejecuta:
```bash
exec "$DIR/.venv-pulpo/bin/pulpo" server ui --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
```

**`.venv-pulpo/`** — venv con instalación editable de pulpo:
```bash
uv pip install -e . --python .venv-pulpo/bin/python
```
Al ser editable, apunta directamente a `_/pulpo/` — cualquier cambio en el
código fuente se refleja en el próximo request sin reinstalar.

### Variables de entorno (en `_/.env`, gitignoreado)

```
ADMIN_PASSWORD=...
BACKEND_PORT=8000
ENABLE_BOTS=true
FRONTEND_DIST=/Users/josetabuyo/Development/pulpo/_/frontend/dist
GOOGLE_SERVICE_ACCOUNT_JSON=...
```

### Comandos de operación

```bash
# Bajar prod de forma segura (SIGTERM — WhatsApp guarda perfil Chrome)
./stop-backend.sh

# Levantar prod
./start.sh back

# Restart seguro (stop + sleep 3 + start)
./restart-backend.sh

# Recargar launchd (después de cambiar el plist)
launchctl kickstart -k "gui/$(id -u)/com.josetabuyo.pulpo"
```

## Reglas para cambios en producción

1. **Cambios de código** → solo hacer `git pull` en `_/`. El próximo request usa el nuevo código
   (instalación editable). Para que el proceso tome los cambios, hacer `./restart-backend.sh`.

2. **Cambios de dependencias** → `uv add <paquete>` actualiza `pyproject.toml` + `uv.lock`.
   Luego `uv pip install -e . --python .venv-pulpo/bin/python` para actualizar `.venv-pulpo/`.

3. **Cambios en `.env`** → editar el archivo y hacer `./restart-backend.sh`.

4. **NUNCA `pkill -9` en procesos Playwright/Chromium** — SIGKILL corrompe el perfil Chrome
   de los bots WhatsApp. Siempre usar `./stop-backend.sh` (SIGTERM).

## Consecuencias

- **El frontend en dev** corre aparte via `./start.sh front` (Vite en 5173).
- **En producción real con dominio propio**, `FRONTEND_DIST` apunta al build estático
  y `pulpo server ui` lo sirve integrado en el mismo proceso del 8000.
- **No hay Docker, no hay CI/CD** — el flujo es git pull + restart. Suficiente para la
  escala actual. Si el proyecto crece, este ADR es el punto de partida para
  evaluar containerización.
