# Estado: Problema de conexión WhatsApp (Watchdog)

## Problema
El bot se desconectaba solo segundos después de conectarse exitosamente via QR.

## Causa raíz
El **watchdog** (corre cada 30s) llama a `getState()` del cliente de WhatsApp justo después de que el evento `ready` dispara. En ese momento, WhatsApp aún está estabilizando la sesión y `getState()` devuelve `OPENING` o `null` en vez de `CONNECTED`. El watchdog interpretaba eso como caída y mataba la sesión recién creada.

## Fixes aplicados (en `index.js`)

### Fix 1 — Grace period 60s
```js
if (session.readyTime && Date.now() - session.readyTime < 60000) continue;
```
**Problema:** no alcanzó — el watchdog disparó 90 segundos después de `ready`.

### Fix 2 — Grace period 2 min + ignorar null/OPENING (ACTUAL)
```js
if (session.readyTime && Date.now() - session.readyTime < 120000) continue;
// null = inicializando, OPENING = transicionando — ignorar ambos
if (state === null || state === 'OPENING') continue;
if (state !== 'CONNECTED') throw new Error(state);
```

## Estado actual
- ✅ Fix aplicado en `index.js` (líneas ~346-356)
- ⚠️ **Pendiente: reiniciar el servidor** para que el fix entre en efecto
- ⚠️ **Pendiente: escanear QR nuevamente** (la sesión actual está caída)
- Los teléfonos de GM Herrería nunca se conectaron aún

## Pasos para retomar
1. Reiniciar el servidor (`npm start` o desde el monitor)
2. Abrir `http://localhost:3000`
3. Vincular QR del teléfono `bot_test` (5491155612767)
4. Esperar 3+ minutos y verificar que el watchdog NO reconecte
5. Si sigue estable → vincular los teléfonos de GM Herrería

## Si vuelve a fallar
Revisar el log en `monitor/monitor.log`. Si el watchdog sigue disparando, aumentar el grace period a 180s o deshabilitar el watchdog temporalmente para confirmar que el problema viene de ahí.
