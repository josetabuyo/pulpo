# Handoff: Reconectar sesión wavi desde la UI

## Qué hay que hacer

Agregar un botón **Reconectar** en la fila de una conexión WhatsApp (wavi) cuando su estado es `stopped`.
Al clickear, el backend levanta el daemon Chrome de esa sesión. Si el teléfono recuerda el dispositivo, queda `ready` sin QR. Si no, redirige a la página del QR.

Una sola historia, dos partes: backend (nuevo endpoint) + frontend (botón en el card).

---

## Estado actual

### El problema concreto

`POST /wavi/sessions` (el endpoint que crea/conecta sesiones) **siempre pasa `--new`**:

```python
# backend/api/wavi.py  línea ~52
async def _connect_and_cleanup(session: str):
    await wd.connect(session, new=True)   # ← --new borra el perfil y fuerza QR nuevo
```

`--new` crea un perfil desde cero. Para *reconectar* una sesión existente caída hay que llamar con `new=False` (sin el flag), lo que retoma el perfil Chrome guardado.

### Lo que hay en el frontend

`WaviConnectionsList` (en `frontend/src/components/bot/WaviConnections.jsx`) muestra cada conexión como una fila estática. Tiene el botón de eliminar (`✕`) pero no tiene "Reconectar".

```jsx
// WaviConnections.jsx  línea 13-24
{conns.map(conn => (
  <div key={conn.id} ...>
    <span>📱</span>
    <span>{conn.number}</span>
    <span>{conn.status || 'stopped'}</span>
    {mode === 'admin' && (
      <button onClick={() => onDelete(conn.number)}>✕</button>
    )}
  </div>
))}
```

`BotCard.jsx` usa `WaviConnectionsList` así:

```jsx
// BotCard.jsx  línea 233
<WaviConnectionsList conns={waviConns} mode={mode} onDelete={handleDeleteWavi} />
```

---

## Lo que hay que hacer

### 1. Backend — nuevo endpoint `POST /wavi/sessions/{session}/connect`

**Archivo:** `backend/api/wavi.py`

Agregar después de la función `_connect_and_cleanup` existente:

```python
# Reconectar sesión existente (sin --new — no borra el perfil Chrome)
@router.post("/wavi/sessions/{session}/connect", dependencies=[Depends(require_admin)])
async def reconnect_wavi_session(session: str):
    session = _validate_session(session)
    if session not in _CONNECTING_SESSIONS:
        _CONNECTING_SESSIONS.add(session)
        asyncio.create_task(_reconnect_and_cleanup(session))
    return {"ok": True, "qr_url": "/api/wavi/qr-page", "status": "connecting", "session": session}


async def _reconnect_and_cleanup(session: str):
    try:
        await wd.connect(session, new=False)   # retoma perfil existente
    finally:
        _CONNECTING_SESSIONS.discard(session)
```

También actualizar `get_wavi_session` para que incluya el campo `connecting` (ya lo tiene, no hay que cambiarlo).

### 2. Frontend — botón Reconectar en `WaviConnectionsList`

**Archivo:** `frontend/src/components/bot/WaviConnections.jsx`

Agregar prop `onReconnect` y mostrar el botón solo cuando `conn.status !== 'ready'`:

```jsx
export function WaviConnectionsList({ conns, mode, onDelete, onReconnect }) {
  if (conns.length === 0) return null
  return (
    <div>
      <div className="ec-section-label" style={{ background: '#f0fdf4', color: '#15803d' }}>WhatsApp</div>
      {conns.map(conn => (
        <div key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', fontSize: 13 }}>
          <span style={{ color: conn.status === 'ready' ? '#22c55e' : '#94a3b8' }}>📱</span>
          <span style={{ flex: 1 }}>{conn.number}</span>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>{conn.status || 'stopped'}</span>
          {mode === 'admin' && conn.status !== 'ready' && (
            <button
              className="btn-sm"
              style={{ background: '#f0fdf4', color: '#15803d' }}
              onClick={() => onReconnect?.(conn.number)}
            >
              Reconectar
            </button>
          )}
          {mode === 'admin' && (
            <button
              className="btn-sm"
              style={{ color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}
              onClick={() => onDelete(conn.number)}
            >✕</button>
          )}
        </div>
      ))}
    </div>
  )
}
```

### 3. Frontend — handler en `BotCard.jsx`

**Archivo:** `frontend/src/components/BotCard.jsx`

Agregar el handler junto a `handleDeleteWavi` (alrededor de línea 100):

```jsx
async function handleReconnectWavi(number) {
  await apiCall('POST', `/wavi/sessions/${number}/connect`, null).catch(() => null)
  onRefresh?.()
}
```

Y pasarlo a `WaviConnectionsList` (alrededor de línea 233):

```jsx
<WaviConnectionsList
  conns={waviConns}
  mode={mode}
  onDelete={handleDeleteWavi}
  onReconnect={handleReconnectWavi}
/>
```

---

## Flujo completo

```
Usuario clickea "Reconectar" en la fila de 5491155612767 (stopped)
  → POST /wavi/sessions/5491155612767/connect
  → backend: _CONNECTING_SESSIONS.add("5491155612767")
  → asyncio.create_task(_reconnect_and_cleanup("5491155612767"))
     → wd.connect("5491155612767", new=False)
       → subprocess: wavi connect 5491155612767  (sin --new)
          Caso A — teléfono recuerda dispositivo: Chrome levanta, WA carga, daemon queda vivo
          Caso B — teléfono desvinculó el dispositivo: Chrome abre WA con QR
     → _CONNECTING_SESSIONS.discard("5491155612767")
  → frontend: onRefresh() → re-fetch del bot → status cambia a ready (Caso A)
               o el usuario abre /wavi/qr-page para escanear (Caso B)
```

En Caso B la UI ya tiene `/api/wavi/qr-page` — es la misma ruta que usa el flujo de conexión nueva. No hay que agregar nada más para el QR.

---

## Tests a correr antes y después

```bash
cd backend
pytest tests/test_wavi_api.py tests/test_wavi_dedup.py -v
```

Los tests existentes no tocan el nuevo endpoint — deben pasar sin cambios.

---

## Notas

- `number` en `BotCard` es el nombre de la sesión wavi (ej: `5491155612767`), que coincide exactamente con el directorio en `WAVI_SESSIONS_DIR`. El endpoint usa ese string directo.
- `_CONNECTING_SESSIONS` es un set global — si el usuario clickea dos veces, la segunda llamada es no-op (el `if session not in _CONNECTING_SESSIONS` lo previene).
- `onRefresh?.()` se llama inmediatamente después del POST, pero la reconexión es async (tarda unos segundos). La UI va a mostrar el estado anterior momentáneamente — está bien, es consistente con cómo funciona la conexión de Telegram.
- El campo `status` de una conexión wavi viene del poller (`wavi_poller.py`) que corre cada 300s. Después de reconectar, el status puede tardar hasta 300s en actualizarse a `ready` en la UI. Si eso molesta, se puede forzar un poll inmediato, pero no es necesario para el MVP.
