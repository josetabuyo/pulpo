# ADR-002: Cuatro interfaces para cuatro contextos de uso

**Estado:** Aceptado — implementado en producción (2026-06-30)

## Contexto

El mismo servidor necesita ser accesible de cuatro formas distintas:
- desde el navegador (admin y portales de bots)
- desde una CLI para operaciones en servidor
- desde código Python de terceros
- como API HTTP pura para integraciones

Mezclar todo en un solo entrypoint complica el testing y hace que cambios
en la UI rompan el API o viceversa.

## Decisión

`pulpo/interfaces/` tiene cuatro submódulos independientes:

| Interface | Módulo | Entrypoint | Uso |
|-----------|--------|------------|-----|
| `api` | `pulpo.interfaces.api` | `pulpo server api` | FastAPI puro — 17 routers bajo `/api` |
| `ui` | `pulpo.interfaces.ui` | `pulpo server ui` | API + monta SPA del frontend |
| `cli` | `pulpo.interfaces.cli` | `pulpo` (script) | Comandos: `serve`, `status`, `db init` |
| `lib` | `pulpo.interfaces.lib` | `import PulpoClient` | Python API in-process |

**Producción usa `pulpo server ui`** (la interfaz `ui`) que sirve tanto el API como el SPA.

## Reglas para cambios

1. **Nuevo endpoint HTTP** → va en `pulpo/interfaces/api/routers/`. Si necesita autenticación
   de admin, usa `Depends(require_admin)` del módulo `deps.py`. Si es pública para el portal
   del bot, va en `pulpo/interfaces/ui/routers/`.

2. **Nuevo comando CLI** → va en `pulpo/interfaces/cli/commands/` y se registra en `main.py`.

3. **Lógica de negocio** → va en `pulpo/business/`. Nunca directamente en una interfaz.
   Las interfaces solo coordinan: reciben requests, llaman a `business/`, devuelven respuestas.

4. **No mezclar interfaces:** un router de `api/` no importa de `ui/` y viceversa.

## Consecuencias

- El frontend (Vite dev server en 5173) hace proxy de `/api` a `localhost:8000`.
- En producción, `pulpo server ui` sirve el SPA compilado desde `FRONTEND_DIST`.
- Si en el futuro se quiere un mobile app, agrega `pulpo/interfaces/mobile/` sin
  tocar nada del resto.
