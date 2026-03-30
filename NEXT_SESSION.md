# NEXT_SESSION — Summarizer online automático + full-sync con fecha desde

**Worktree:** `_` (master / producción) — necesita WA Web real para testear scraping.
**Rama:** master
**Prioridad:** alta

---

## Pedido del usuario (resumen exacto)

> "poder indicar un parametro de fecha desde para el full sync, y dejar el botón de full sync normalizado en todas las ui, no quiero otro botón, el otro evento debería ser automático, cuando el servidor arranca y en cada momento del pulling, deberíamos tomar todos los mensajes desde el ultimo que capturamos hasta el ultimo de los nuevos que entraron, es siempre ese método el 'online' del summarizer, y el otro método es el full-sync, no quiero otro, borremos basura"

---

## Estado actual (lo que existe hoy)

### Endpoints de sync (`backend/api/whatsapp.py`)
- `POST /wa/full-sync` → `_run_sync(scroll_rounds=50)` — scrapea historial completo
- `POST /wa/recent-sync` → `_run_sync(scroll_rounds=0)` — scrapea solo vista actual ← **BORRAR**
- `GET /wa/sync-status` → `{"running": bool}`
- `_run_sync(scroll_rounds)` — función compartida que itera contactos, llama `scrape_full_history`

### UI (EmpresaCard.jsx — botón "Re-Sync" en SummaryModal)
- El modal del summarizer tiene un botón "Re-Sync {nombre}" o "Re-Sync todos"
- Actualmente llama `POST /api/summarizer/{empresa_id}/sync` (sync de DB, no WA scraping)
- Hay que unificarlo con `/api/wa/full-sync` (scraping WA Web real)

### Polling online (whatsapp.py)
- `_poll_open_chat` Python: cada 3s escanea sidebar → detecta mensajes nuevos → `_on_message(from_poll=False)` → acumula en summarizer (fix reciente, 2026-03-25)
- `pollSidebar` JS: cada 2s observa cambios en sidebar → `from_poll=True` (solo loguea en DB)
- `pollOpenChat` JS: cada 2s → solo si el chat está abierto → `from_poll=False`

**Limitación del poller actual**: lee `span[title]` del sidebar (preview posiblemente truncado, sin timestamp real, no detecta audios ni imágenes).

---

## Lo que hay que hacer

### 1. Borrar `/wa/recent-sync`
El endpoint `/wa/recent-sync` desaparece. `_run_sync` ya no necesita el parámetro `scroll_rounds=0`.
Verificar que no haya botón en la UI para "recent-sync".

### 2. Full-sync con `from_date` y `contact_phone` opcionales

**API:** `POST /wa/full-sync`
```json
{
  "from_date": "2026-03-01",     // opcional, ISO date — para de scrollear antes de esta fecha
  "contact_phone": "5491100000000"  // opcional — sincronizar solo este contacto
}
```

**`_run_sync(from_date: date | None = None, contact_phone: str | None = None)`**

Cuando `from_date` está presente, `scrape_full_history` para de scrollear cuando todos los
mensajes del batch son anteriores a `from_date`. Esto reduce los scrolls necesarios.

### 3. Auto-sync al arrancar el servidor — algoritmo de delta incremental

**NO usar fecha hardcodeada.** El criterio es por contenido: avanzar del mensaje más nuevo
al más viejo y parar en el primero que ya esté guardado en DB.

**Algoritmo (delta scan):**
```
Para cada contacto con summarizer activo:
  Abrir el chat en WA Web
  Leer batch de mensajes visibles (sin scroll adicional primero)
  Para cada mensaje, de más nuevo a más viejo:
    ¿Está ya en DB? (check por timestamp + body + phone)
      SÍ → stop — ya estamos al día para este contacto
      NO → guardar en DB + acumular en summarizer
  Si todos los mensajes del batch eran nuevos → scrollear un paso hacia arriba y repetir
  Si llegamos al tope del chat (no hay más) → stop
Reportar: contacto X — N mensajes nuevos procesados, M ya existían, paró en [timestamp]
```

**¿Por qué este criterio?**
- No asume ningún rango de fechas — siempre encuentra el límite exacto
- Funciona correctamente tras reinicios cortos (pocas horas) o largos (días)
- Para automáticamente al llegar al primer mensaje ya procesado → eficiente
- Equivale a "dame todo lo que me perdí, sin importar cuánto tiempo pasó"

**Check de "ya está en DB":**
```python
# Usar log_message_historic que ya retorna False si el mensaje existe
saved = await log_message_historic(eid, bot_phone, phone, name, body, timestamp, outbound)
if not saved:
    break  # encontramos el primer mensaje ya existente → stop
```

`log_message_historic` ya hace upsert/dedup por `(bot_id, phone, timestamp, body)`.
Si retorna `False` = ya existía → es el punto de corte.

**Implementación en main.py:**
```python
async def _startup_sync():
    await asyncio.sleep(15)  # esperar que los bots se reconecten
    await _run_delta_sync()   # delta incremental, sin from_date

asyncio.create_task(_startup_sync())
```

**`_run_delta_sync(contact_phone=None)`** — nueva función separada de `_run_sync`:
- Igual que `_run_sync` pero en el loop de mensajes: si `log_message_historic` retorna False → break
- Reporta por contacto: cuántos nuevos vs cuántos ya existían
- No borra el .md (no resetea el summarizer, solo agrega lo nuevo)

### 4. UI — date picker en SummaryModal

- Input `type="date"` con default = hoy - 30 días
- El botón "Re-Sync" pasa `from_date` y `contact_phone` en el body
- La llamada debe ser a `/api/wa/full-sync` (scraping WA), no a `/api/summarizer/{id}/sync` (DB backfill)

---

## Arquitectura — cambios por archivo

### `backend/api/whatsapp.py`
```python
# BORRAR:
@router.post("/recent-sync", ...)

# AGREGAR modelo:
class FullSyncBody(BaseModel):
    from_date: date | None = None
    contact_phone: str | None = None

# MODIFICAR endpoint:
@router.post("/full-sync", ...)
async def full_sync(body: FullSyncBody = FullSyncBody(), ...):
    background_tasks.add_task(_run_sync, from_date=body.from_date, contact_phone=body.contact_phone)

# MODIFICAR _run_sync:
async def _run_sync(from_date: date | None = None, contact_phone: str | None = None) -> None:
    # Si contact_phone → filtrar solo ese contacto en la iteración
    # Pasa from_date a scrape_full_history
```

### `backend/automation/whatsapp.py`
```python
# En scrape_full_history: agregar from_date como parámetro de parada temprana
async def scrape_full_history(self, session_id, contact_name, scroll_rounds=50,
                               doc_save_dir=None, from_date: date | None = None):
    # En el loop de scroll: si from_date y todos los msgs del batch son < from_date → break
    # Reduce scrolls: en lugar de 50 fijos, para cuando ya tenemos todo lo necesario
```

### `backend/main.py`
```python
# En lifespan, después de restaurar sesiones WA:
async def _startup_sync():
    await asyncio.sleep(15)
    await _run_delta_sync()  # delta incremental: más nuevo → más viejo, para en el primero ya guardado

asyncio.create_task(_startup_sync())
```

### `backend/api/whatsapp.py` — nueva función `_run_delta_sync`
```python
async def _run_delta_sync(contact_phone: str | None = None) -> None:
    """
    Sync incremental: para cada contacto, escanea mensajes de más nuevo a más viejo
    y para en cuanto encuentra uno ya guardado en DB.
    No borra el .md — solo agrega lo nuevo.
    Reporta: cuántos nuevos, cuántos ya existían, en qué timestamp paró.
    """
    global _sync_running
    if _sync_running:
        return
    _sync_running = True
    mode = "delta-sync"
    try:
        for session_id, state in list(clients.items()):
            # ... iterar contactos con summarizer activo ...
            messages = await wa_session.scrape_full_history(
                session_id, contact_name,
                scroll_rounds=10,  # máximo razonable, pero el break interno para antes
                doc_save_dir=_doc_dir,
            )
            # Ordenar de más nuevo a más viejo
            messages.sort(key=lambda m: m.get("timestamp") or "", reverse=True)
            new_count = 0
            stop_ts = None
            for msg in messages:
                saved = await log_message_historic(...)
                if not saved:
                    stop_ts = msg["timestamp"]
                    break  # primer mensaje ya existente → stop
                new_count += 1
                # acumular en summarizer
            _log.info(f"[{mode}] '{contact_name}': {new_count} nuevos, paró en {stop_ts or 'tope del chat'}")
    finally:
        _sync_running = False
```

### `frontend/src/components/EmpresaCard.jsx`
- `SummaryModal`: agregar input `type="date"` encima del botón Re-Sync
- Cambiar la llamada de `POST /api/summarizer/{id}/sync` a `POST /api/wa/full-sync`
- Pasar `{ from_date, contact_phone }` en el body

---

## Tests TDD — orden obligatorio

### 1. Correr tests existentes (línea de base)
```bash
cd /Users/josetabuyo/Development/pulpo/_/backend
pytest tests/ -v
```

Ver `tests/test_whatsapp_sync.py` y `tests/test_summarizer.py`.

### 2. Escribir tests nuevos ANTES de implementar

**`tests/test_whatsapp_sync.py`** — agregar:
```python
# /wa/recent-sync ya no existe (404)
async def test_recent_sync_removed(client):
    r = await client.post("/api/wa/recent-sync")
    assert r.status_code in (404, 405)

# /wa/full-sync acepta from_date sin error
async def test_full_sync_accepts_from_date(client):
    r = await client.post("/api/wa/full-sync", json={"from_date": "2026-03-01"})
    assert r.status_code == 200

# /wa/full-sync acepta contact_phone sin error
async def test_full_sync_accepts_contact_phone(client):
    r = await client.post("/api/wa/full-sync", json={"contact_phone": "5491100000000"})
    assert r.status_code == 200

# /wa/sync-status sigue funcionando
async def test_sync_status(client):
    r = await client.get("/api/wa/sync-status")
    assert r.status_code == 200
    assert "running" in r.json()
```

### 3. Correr tests de nuevo (todo en verde)

### 4. Reiniciar backend y verificar auto-sync en log
```bash
./restart-backend.sh
# Esperar 15s y buscar:
grep "startup.*sync\|Iniciando" monitor/backend.log | tail -5
```

---

## Riesgos

- **`log_message_historic` como señal de corte**: si retorna False por un motivo distinto a "ya existe" (ej. error de DB) → break prematuro. Verificar que la función retorna False estrictamente para "ya existía" y levanta excepción para errores.
- **Mensajes sin timestamp**: si WA Web no provee timestamp para un mensaje → el match en DB puede fallar. Tratar `None` timestamp como "siempre nuevo" (no cortar).
- **`from_date` en full-sync**: el scraper obtiene timestamps en formato WA ("HH:MM, DD/MM/YYYY") — parsear correctamente antes de comparar con `date`.
- **Dedup**: el delta-sync de startup y el poller Python pueden correr simultáneamente → el `_sync_running` lock previene doble sync.
- **Contacto sin mensajes en DB**: delta-sync va a procesar todo hasta el tope del chat (no hay punto de corte) → scroll_rounds=10 como límite superior razonable.

---

## Archivos clave a leer al iniciar la sesión

1. `backend/api/whatsapp.py` (líneas 346–530)
2. `backend/automation/whatsapp.py` (buscar `scrape_full_history`)
3. `backend/tests/test_whatsapp_sync.py`
4. `backend/main.py` (lifespan)
5. `frontend/src/components/EmpresaCard.jsx` (SummaryModal, líneas 69–192)

---

## Checklist

- [ ] Correr tests existentes (línea de base — tienen que estar verdes antes de tocar nada)
- [ ] Escribir tests nuevos (TDD — en rojo primero):
  - [ ] `test_recent_sync_removed` → 404
  - [ ] `test_full_sync_accepts_from_date` → 200
  - [ ] `test_full_sync_accepts_contact_phone` → 200
  - [ ] `test_delta_sync_stops_at_existing` → mock `log_message_historic` retornando False en el 3er mensaje → verificar que solo se procesaron 2
- [ ] Borrar `/wa/recent-sync`
- [ ] Implementar `_run_delta_sync` con el algoritmo nuevo→viejo + break en primer existente
- [ ] Agregar `from_date` y `contact_phone` a `_run_sync` y `scrape_full_history`
- [ ] Auto-sync en startup (main.py lifespan → `_run_delta_sync`)
- [ ] UI: date picker en SummaryModal + llamada a `/api/wa/full-sync`
- [ ] Correr todos los tests (verde)
- [ ] Reiniciar backend, esperar 15s, verificar en log: "delta-sync ... N nuevos, paró en ..."

## Estado: **LISTO PARA MERGE**

## Puertos
- Backend: `:8001` | Frontend: `:5174` | `ENABLE_BOTS=false`

## Arrancar
```bash
./start.sh  # desde /Users/josetabuyo/Development/pulpo/feat-empresa-card
```

---

## Objetivo

Crear un componente `EmpresaCard` unificado que funcione en dos contextos:

| Contexto | Ruta | Prop |
|---|---|---|
| Dashboard admin | `/dashboard` | `mode="admin"` |
| Portal empresa  | `/empresa`   | `mode="empresa"` |

**Lo más importante:** el admin habilita/deshabilita herramientas para cada empresa con un toggle. Las empresas solo ven las herramientas con `activa === true`.

---

## Estado del trabajo

### ✅ Ya hecho en este worktree:

**`frontend/src/components/EmpresaCard.jsx`** — componente nuevo completo:
- Tabs: Conexiones / Herramientas / Contactos / Configurar (solo empresa)
- `mode="admin"`: callbacks al padre para modales, drag&drop support, toggle tools
- `mode="empresa"`: self-contained — QR inline, add WA/TG inline, config inline
- `normalizeBot(bot)` helper exportado (convierte formato admin → canónico)
- SimChat integrado en admin+simMode+connected
- Toggle switch para habilitar/deshabilitar tools (solo admin)
- Sub-componentes: ConnectionRow, ToolRow, ToolForm, SummaryModal, ContactModal, EmpresaConfigTab, Toggle

**`frontend/src/index.css`** (primeras líneas):
- Import Google Fonts: DM Sans + JetBrains Mono
- CSS variables: `--brand`, `--bg`, `--surface`, `--border`, `--text-muted`, `--font-mono`, etc.
- Body font actualizado a DM Sans

### ✅ Completado en esta sesión:

**`frontend/src/index.css`** — CSS `ec-*` agregado al final

**`frontend/src/pages/DashboardPage.jsx`** — Actualizado:
- Import de `EmpresaCard` y `normalizeBot`
- Eliminados `PhoneRow`, `TelegramRow`, `STATUS_LABELS` (dead code)
- `bots.map` reemplazado por `<EmpresaCard mode="admin" ...>`
- `onDrop` actualizado para usar `.ec-card` en lugar de `.bot-block`

**`frontend/src/pages/EmpresaPage.jsx`** — Simplificado (1249 → ~165 líneas):
- Eliminados todos los componentes duplicados: `ConexionCard`, `ConfigView`, `HerramientasSection`, `ToolModal`, `SummaryModal`, `ContactModal`, `ContactosSection`, `ContactChat`, `connectAndPollEmpresa`
- `EmpresaDashboard` reescrito: solo carga datos y renderiza `<EmpresaCard mode="empresa" ...>`
- Se mantiene: `EmpresaLogin`, auth (login/logout/refresh), `empresaApi`, polling

**Testeado en simulador**:
- Dashboard admin: 3 EmpresaCards con tabs, badges WA/TG, SimChat, botones de acción ✅
- Portal empresa: tabs Conexiones/Herramientas/Contactos/Configurar, add canal inline ✅

### ⚠️ Pendiente conocido (backend):

`/api/empresas/{botId}/tools` retorna 401 desde modo admin — el backend acepta solo JWT empresa, no `x-password`. Las cards muestran "0 herramientas" pero no crashean.

**TODO backend**: agregar `x-password` admin auth a los routers de tools.

---

## CSS a agregar al FINAL de `index.css`

```css
/* ─── EmpresaCard ─────────────────────────────────────────────── */

.ec-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 20px;
  background: white;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
  transition: box-shadow .2s;
}
.ec-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.09); }
.ec-card.drag-over {
  outline: 2px dashed #7c3aed;
  outline-offset: -2px;
  background: #faf5ff;
}
.ec-header {
  background: linear-gradient(135deg, #faf5ff 0%, #f8fafc 100%);
  border-bottom: 1px solid #e8e0f0;
  padding: 14px 20px;
}
.ec-header-main { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.ec-header-info { flex: 1; min-width: 0; }
.ec-header-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 3px; }
.ec-bot-name { font-size: 15px; font-weight: 700; color: #1e1b4b; letter-spacing: -.3px; }
.ec-bot-id {
  font-size: 11px; color: #94a3b8; background: #f1f5f9;
  padding: 2px 8px; border-radius: 20px;
  font-family: var(--font-mono); letter-spacing: .2px;
}
.ec-sim-mode-badge {
  font-size: 10px; font-weight: 700; color: #92400e;
  background: #fef3c7; border: 1px solid #fcd34d;
  padding: 2px 8px; border-radius: 20px; letter-spacing: .5px;
}
.ec-bot-msg {
  font-size: 12px; color: #64748b; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 520px;
}
.ec-header-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.ec-status-dots { display: flex; gap: 5px; align-items: center; }
.ec-status-dot {
  width: 9px; height: 9px; border-radius: 50%; cursor: help; flex-shrink: 0;
  box-shadow: 0 0 0 2px white;
}
.ec-header-actions { display: flex; gap: 6px; }
.ec-tabs {
  display: flex; border-bottom: 1px solid #e8e8f0;
  background: white; padding: 0 16px; overflow-x: auto;
}
.ec-tab {
  display: flex; align-items: center; gap: 6px; padding: 10px 14px;
  font-size: 13px; font-weight: 500; color: #94a3b8;
  background: none; border-radius: 0;
  border-bottom: 2px solid transparent; margin-bottom: -1px; white-space: nowrap;
  transition: color .15s, border-color .15s;
}
.ec-tab:hover { color: #7c3aed; opacity: 1; }
.ec-tab--active { color: #7c3aed; border-bottom-color: #7c3aed; }
.ec-tab-badge {
  font-size: 10px; font-weight: 700; background: #ede9fe; color: #7c3aed;
  padding: 1px 6px; border-radius: 10px; min-width: 18px; text-align: center;
}
.ec-tab--active .ec-tab-badge { background: #7c3aed; color: white; }
.ec-content { padding: 0; }
.ec-section-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .7px; padding: 5px 20px 4px; border-bottom: 1px solid #f0f0f0;
}
.ec-section-label--wa { color: #059669; background: #f0fdf4; border-top: 1px solid #d1fae5; }
.ec-section-label--tg { color: #1d4ed8; background: #eff6ff; border-top: 1px solid #dbeafe; }
.ec-conn-row { border-bottom: 1px solid #f0f2f5; }
.ec-conn-row:last-of-type { border-bottom: none; }
.ec-conn-row.dragging { opacity: .4; }
.ec-conn-main { display: flex; align-items: center; padding: 10px 20px; gap: 10px; flex-wrap: wrap; }
.ec-chan-badge {
  display: inline-flex; align-items: center;
  font-size: 10px; font-weight: 700; padding: 2px 6px;
  border-radius: 4px; letter-spacing: .3px; flex-shrink: 0;
}
.ec-chan-badge--wa { background: #25d366; color: white; }
.ec-chan-badge--tg { background: #229ed9; color: white; }
.ec-conn-id {
  font-size: 13px; font-weight: 500; color: #1e293b;
  min-width: 110px; font-family: var(--font-mono); letter-spacing: -.3px;
}
.ec-conn-override { font-size: 11px; color: #94a3b8; font-style: italic; }
.ec-sim-badge {
  font-size: 10px; font-weight: 700; color: #92400e;
  background: #fef3c7; border: 1px solid #fde68a;
  padding: 2px 6px; border-radius: 4px; letter-spacing: .5px;
}
.ec-conn-actions { display: flex; gap: 6px; align-items: center; margin-left: auto; flex-wrap: wrap; }
.ec-conn-hint { font-size: 12px; color: #94a3b8; }
.ec-qr-inline {
  padding: 16px 20px; text-align: center;
  background: #faf5ff; border-top: 1px solid #ede9fe;
}
.ec-add-row {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 20px; border-top: 1px dashed #e8e8f0;
}
.ec-tools-summary { font-size: 12px; color: #94a3b8; margin-left: 4px; }
.ec-add-forms { border-top: 1px solid #e8e8f0; }
.ec-add-form-row { display: flex; gap: 12px; padding: 12px 20px; flex-wrap: wrap; }
.ec-tool-row {
  display: flex; align-items: center; padding: 12px 20px;
  border-bottom: 1px solid #f0f2f5; transition: background .15s;
}
.ec-tool-row:hover { background: #fafafc; }
.ec-tool-row--off { opacity: .6; }
.ec-tool-row:last-of-type { border-bottom: none; }
.ec-tool-main { display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 12px; }
.ec-tool-info { display: flex; align-items: center; gap: 8px; flex: 1; flex-wrap: wrap; }
.ec-tool-name { font-size: 14px; font-weight: 600; color: #1e293b; }
.ec-tool-type {
  font-size: 11px; color: #64748b; background: #f1f5f9;
  padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.ec-tool-scope { font-size: 12px; color: #94a3b8; }
.ec-tool-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ec-tool-status-badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 12px; }
.ec-tool-status-badge--on  { background: #ecfdf5; color: #059669; }
.ec-tool-status-badge--off { background: #f1f5f9; color: #94a3b8; }
.ec-toggle {
  width: 42px; height: 24px; border-radius: 12px;
  position: relative; cursor: pointer; border: none; padding: 0;
  transition: background .2s; flex-shrink: 0;
}
.ec-toggle--on  { background: #7c3aed; }
.ec-toggle--off { background: #cbd5e1; }
.ec-toggle:disabled { opacity: .4; cursor: not-allowed; }
.ec-toggle::after {
  content: ''; position: absolute; top: 3px;
  width: 18px; height: 18px; border-radius: 50%;
  background: white; transition: left .2s;
  box-shadow: 0 1px 3px rgba(0,0,0,.2);
}
.ec-toggle--on::after  { left: calc(100% - 21px); }
.ec-toggle--off::after { left: 3px; }
.ec-config-tab { padding: 20px; }
.ec-btn-active { background: #ede9fe !important; color: #7c3aed !important; }
.error { font-size: 13px; color: #c00; }
```

---

## ⚠️ Nota backend (importante)

Los endpoints de tools (`/api/empresas/{botId}/tools`, `/api/tools/{id}/toggle`) actualmente requieren **JWT empresa**. Para que el admin pueda manejar tools de una empresa, el backend debe aceptar también **`x-password`** en esos endpoints.

Si el backend no lo soporta todavía, las llamadas de tools en modo admin van a retornar 401. Diseñar el error para que sea evidente al usuario.

**TODO backend**: agregar `x-password` admin auth a los routers de tools.

---

## Lo que NO hacer
- No tocar `data/sessions/` (no existen — ENABLE_BOTS=false)
- No hacer push a origin (lo hace la sesión de `_`)
- No mergear directamente a master

## Merge
Cuando esté listo, avisarle a la sesión de `_` para merge + push.
