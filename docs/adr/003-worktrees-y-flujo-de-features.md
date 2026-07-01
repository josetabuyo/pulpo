# ADR-003: Features en worktrees, merge siempre desde master

**Estado:** Aceptado — en uso desde marzo 2026

## Contexto

El servidor de producción (`_/`, puerto 8000) tiene bots de WhatsApp y Telegram
activos con sesiones persistentes. Desarrollar directamente en master arriesga
interrumpir esas sesiones o enviar mensajes reales a clientes durante el desarrollo.

## Decisión

Cada feature se desarrolla en un worktree Git separado con su propio puerto y
base de datos aislada. El worktree corre en **modo simulado** (`ENABLE_BOTS=false`).

### Ciclo de vida obligatorio

```
1. Crear worktree
   git worktree add /Users/josetabuyo/Development/pulpo/<rama> -b <rama>

2. Setup (symlinks + .env con puertos únicos)
   ln -s /Users/josetabuyo/Development/pulpo/_/node_modules <wdir>/node_modules
   ln -s /Users/josetabuyo/Development/pulpo/_/phones.json  <wdir>/phones.json
   # NO linkear data/ — cada worktree tiene su propia DB aislada
   mkdir -p <wdir>/data

3. Desarrollar con ENABLE_BOTS=false (simulador de mensajes)

4. Mergear DESDE master (_/)
   git merge <rama> --no-ff -m "feat: ..."
   git push origin master

5. Bajar el backend del worktree ANTES de eliminarlo
   /ruta/al/worktree/stop-backend.sh

6. Eliminar worktree
   git worktree remove <rama>
```

### Puertos asignados

| Worktree     | Backend | Frontend |
|--------------|---------|----------|
| `_` (master) | 8000    | 5173     |
| dev-1        | 8001    | 5174     |
| dev-2        | 8002    | 5175     |
| refactor     | 9004    | —        |

## Por qué el paso 5 es crítico

Un backend activo en un worktree tiene bots conectados. Si se elimina el
worktree sin bajarlo, el proceso uvicorn queda huérfano con bots activos
que pueden responder mensajes reales. Esto ocurrió en producción (incidente abril 2026).

## Consecuencias

- **Nunca desarrollar en `_/` directamente** salvo hotfixes urgentes.
- **El merge lo hace siempre la sesión de `_/`**, nunca un worktree.
- **Usar `ENABLE_BOTS=false`** en todos los worktrees de desarrollo. Usar `ENABLE_BOTS=true`
  solo para tests e2e justo antes del merge, y solo en un worktree con la DB de prod copiada.
- **`_/` es la única fuente de verdad** de producción. Nada toca el servidor de prod
  sin pasar por el guardián (sesión de Claude en `_/`).
