# NEXT_SESSION — wa-v2: WhatsApp Trigger v2 con OpenWA

**Worktree:** `/Users/josetabuyo/Development/pulpo/wa-v2`
**Branch:** `wa-v2`
**Backend:** http://localhost:8003
**Frontend:** http://localhost:5176
**Modo:** simulado (ENABLE_BOTS=false)

---

## Objetivo

Crear un segundo nodo trigger de WhatsApp — **WhatsApp Trigger v2** — que funcione a través de **OpenWA** (`@open-wa/wa-automate` v4.76) en lugar del scraping Playwright manual de v1.

**v1 actual:** ~3700 líneas de Playwright personalizado en `backend/automation/whatsapp.py`, scraping manual del DOM, 5 métodos de descarga de blobs.

**v2 nuevo:** OpenWA corre como sidecar Node.js. Nuestro FastAPI solo recibe webhooks y llama al REST de OpenWA para historial/media. Cero DOM scraping.

**Reglas:**
- v1 (`whatsapp_trigger`) NO se toca. Sigue funcionando en producción.
- v2 (`whatsapp_trigger_v2`) es un nodo nuevo paralelo, convive con v1.
- `canal="whatsapp_v2"` (nuevo valor) — no interfiere con `canal="whatsapp"` de v1.

---

## Arquitectura

```
OpenWA sidecar (Node.js, @open-wa/wa-automate v4.76)
  Un proceso por teléfono:
    npx @open-wa/wa-automate
      --session-id {phone}
      --port {8090+idx}
      --webhook http://localhost:8003/api/wa-v2/inbound
      --headless true
      --session-data-path ./data/wa-v2-sessions

         ↓  POST webhook (nuevo mensaje)
         ↓  GET REST (historial, media)

FastAPI backend (puerto 8003)
  backend/api/whatsapp_v2.py         ← nuevo router
    POST /api/wa-v2/inbound          ← recibe webhook de OpenWA
    GET  /api/wa-v2/status           ← estado de instancias
    POST /api/wa-v2/start/{phone}    ← iniciar instancia
    POST /api/wa-v2/stop/{phone}     ← parar instancia

  backend/automation/whatsapp_v2.py  ← adapter OpenWA
    class WhatsAppV2Manager
      start_instance(phone, port)
      stop_instance(phone)
      send_message(phone, to, text)
      get_history(phone, contact_jid, count=50)
      download_media(phone, msg_id)
      handle_webhook(payload) → run_flows()

  backend/graphs/nodes/whatsapp_trigger_v2.py  ← nodo nuevo
    class WhatsappTriggerV2Node
      config_schema idéntico a v1
      canal: "whatsapp_v2"
```

---

## Archivos a crear (nuevos)

### 1. `backend/automation/whatsapp_v2.py`

Manager que mantiene un dict `_instances: dict[phone → {process, port}]` de procesos OpenWA.

Métodos principales:
- `start_instance(phone, port)` — lanza `npx @open-wa/wa-automate ...` como subprocess
- `stop_instance(phone)` — SIGTERM (nunca SIGKILL)
- `send_message(phone, to_number, text)` — POST a `http://localhost:{port}/api/sendText`
- `get_history(phone, contact_jid, count=100)` — GET REST OpenWA
- `handle_webhook(payload)` — normaliza payload → FlowState → `run_flows()`

**Normalización del payload OpenWA → FlowState:**
```python
# Campos clave del objeto Message de OpenWA:
# payload["from"]               → JID remitente "5491155612767@c.us"
# payload["body"]               → texto (o base64 si es media con --auto-download)
# payload["type"]               → "chat" | "ptt" | "image" | "document"
# payload["isGroupMsg"]         → bool
# payload["sender"]["pushname"] → nombre del contacto
# payload["t"]                  → timestamp unix
# payload["fromMe"]             → ignorar si True
# payload["sessionId"]          → phone number del bot

contact_phone = payload["from"].replace("@c.us", "").replace("@g.us", "")
bot_phone = payload["sessionId"]
state = FlowState(
    canal="whatsapp_v2",
    message=payload["body"],
    contact_phone=contact_phone,
    connection_id=bot_phone,
    ...
)
```

Para media:
- `ptt` → `payload["body"]` es base64 del ogg (si --auto-download activo)
- `image` → `payload["body"]` es base64 del jpg
- `document` → `payload["body"]` es base64 + `payload["filename"]`

### 2. `backend/api/whatsapp_v2.py`

```python
router = APIRouter(prefix="/api/wa-v2", tags=["whatsapp-v2"])

@router.post("/inbound")          # webhook de OpenWA — sin auth (solo localhost)
@router.get("/status")            # lista instancias activas + puertos
@router.post("/start/{phone}")    # inicia instancia OpenWA
@router.post("/stop/{phone}")     # para instancia
@router.post("/send")             # envía mensaje (testing y flows)
```

### 3. `backend/graphs/nodes/whatsapp_trigger_v2.py`

Copiar exactamente `whatsapp_trigger.py` y cambiar:
- Nombre de clase: `WhatsappTriggerV2Node`
- No hay cambios en `config_schema` — es idéntico al de v1

### 4. `start-wa-v2.sh` (raíz del worktree, opcional)

Script para levantar las instancias OpenWA de todos los teléfonos en `phones.json`.
Requiere Node.js >= 22.

---

## Archivos a modificar

### 5. `backend/graphs/nodes/__init__.py`

```python
from .whatsapp_trigger_v2 import WhatsappTriggerV2Node

NODE_REGISTRY = {
    ...existing...,
    "whatsapp_trigger_v2": WhatsappTriggerV2Node,
}

__all__ = [...existing..., "WhatsappTriggerV2Node"]
```

### 6. `backend/graphs/node_types.py`

En `NODE_TYPES`:
```python
"whatsapp_trigger_v2": NodeType(
    id="whatsapp_trigger_v2",
    label="WhatsApp Trigger v2",
    color="#15803d",
    description="Trigger WA vía OpenWA (sin Playwright manual). Usar en flows nuevos.",
),
```

En `_CLASSIFY_SUBSTRINGS` (ANTES del entry de "whatsapp_trigger"):
```python
("whatsapp_trigger_v2", "whatsapp_trigger_v2"),
```

### 7. `backend/graphs/compiler.py`

Línea 24 — `TRIGGER_TYPES`:
```python
TRIGGER_TYPES: frozenset[str] = frozenset({
    "message_trigger", "whatsapp_trigger", "telegram_trigger",
    "whatsapp_trigger_v2",  # ← agregar
})
```

En la validación de canal (~línea 145):
```python
if ctype == "whatsapp_trigger_v2" and state.canal != "whatsapp_v2":
    continue
```

El resto de la lógica (contact_filter, cooldown, message_pattern, connection_id) es idéntica a `whatsapp_trigger`. Reutilizar agrupando en un set: `if ctype in {"whatsapp_trigger", "whatsapp_trigger_v2"}`.

### 8. `backend/main.py`

```python
from api.whatsapp_v2 import router as whatsapp_v2_router
# en app.include_router:
app.include_router(whatsapp_v2_router)
```

### 9. `frontend/src/components/NodeConfigPanel.jsx`

Línea 16 — `TRIGGER_TYPES`:
```javascript
const TRIGGER_TYPES = new Set([
  'whatsapp_trigger', 'whatsapp_trigger_v2',  // ← agregar v2
  'telegram_trigger', 'message_trigger'
])
```

El `connection_select` ya funciona igual para v2 (mismo `connection_id` que v1, mismas conexiones WA).

---

## Verificar antes de empezar

```bash
node --version   # debe ser >= 22.21.0
npx @open-wa/wa-automate@4.76.0 --help   # debe mostrar opciones
```

Si node no está en >= 22, instalar con nvm:
```bash
nvm install 22
nvm use 22
```

---

## Orden de implementación

1. Verificar Node.js >= 22
2. `whatsapp_trigger_v2.py` — copiar v1, cambiar nombre (2 min)
3. `node_types.py` — agregar tipo (5 líneas)
4. `__init__.py` — registrar nodo (3 líneas)
5. `compiler.py` — agregar tipo + canal (10 líneas)
6. `automation/whatsapp_v2.py` — adapter: `handle_webhook` + `send_message` + `get_history`
7. `api/whatsapp_v2.py` — router: POST /inbound + endpoints de gestión
8. `main.py` — registrar router
9. `NodeConfigPanel.jsx` — 1 línea
10. Test manual con curl: `curl -X POST localhost:8003/api/wa-v2/inbound -H "Content-Type: application/json" -d '{...payload...}'`
11. `tests/test_wa_v2.py` — al menos un test del webhook

---

## Puertos

| Servicio | Puerto |
|---|---|
| Backend FastAPI | 8003 |
| Frontend Vite | 5176 |
| OpenWA teléfono 0 | 8090 |
| OpenWA teléfono 1 | 8091 |
| OpenWA teléfono 2 | 8092 |

---

## Notas críticas

- **Nunca SIGKILL a OpenWA** — SIGTERM para que guarde la sesión.
- **Sesiones OpenWA en `data/wa-v2-sessions/`** — gitignoreado, aislado.
- **v1 es intocable** — `backend/automation/whatsapp.py` no se modifica.
- **`canal="whatsapp_v2"`** — nunca usar `"whatsapp"`. Garantiza que v1 y v2 no interfieran.
- **OpenWA v4.76.0 estable** — NO usar v5 alpha.
- El merge a master lo hace siempre la sesión de `_`.

---

## Para arrancar

```bash
cd /Users/josetabuyo/Development/pulpo/wa-v2
./start.sh back   # backend en background, logs en monitor/backend.log
./start.sh front  # frontend
```
