# NEXT SESSION — Tool Sumarizadora

> Decile "dale" a Claude y arranca solo.

## Contexto

Worktree `tool-sumarizadora` creado desde master (commit `0bc6ff0`).
Backend en `:8001`, frontend en `:5174`. `ENABLE_BOTS=false` → simulador activo, sin WA real.

El plan completo está en `management/PLAN_TOOL_SUMARIZADORA.md`. Leelo antes de arrancar.

---

## Misión

Implementar la tool sumarizadora en **modo dangerous**: avanzar lo más posible sin pararse a pedir confirmación. La Fase 2 (descarga de audios reales de WA Web con Playwright) puede quedar incompleta si es muy compleja — se termina en master.

---

## Orden de trabajo

### 0. Arrancar el server
```bash
cd /Users/josetabuyo/Development/pulpo/tool-sumarizadora
./start.sh
```
Verificar que backend levanta en :8001 y frontend en :5174.

### 1. Fase 1 — Tool pasiva acumula texto (MVP)

**Crear `backend/tools/summarizer.py`:**
- `accumulate(empresa_id, contact_phone, contact_name, msg_type, content, timestamp)`
  → append al archivo `data/summaries/{empresa_id}/{contact_phone}.md`
- `get_summary(empresa_id, contact_phone)` → retorna el contenido del .md
- Crear directorio si no existe
- Formato de cada entrada en el .md:
  ```
  ## 2026-03-19 14:32
  **[texto]** <contenido>
  ---
  ```

**Crear `backend/tools/__init__.py`** si no existe (vacío).

**Integrar en `backend/sim.py`:**
- En `sim_receive`, si la tool del contacto es `type: "summarizer"`,
  llamar `summarizer.accumulate(...)`. La tool NO responde, solo acumula.
  No interrumpe otras tools.

**Integrar en `backend/automation/whatsapp.py`:**
- Mismo patrón: si tool es summarizer, acumular, no responder.

**Crear `backend/api/summarizer.py`** — router con:
```
GET  /api/summarizer/{empresa_id}/{contact_phone}   → devuelve el .md como texto plano
GET  /api/summarizer/{empresa_id}                   → lista contactos que tienen resumen
```

**Registrar el router en `backend/main.py`.**

**UI mínima en frontend:**
- Para contactos con tool `summarizer`, mostrar botón "Ver resumen"
- Al clickear: fetch al endpoint → mostrar en modal o drawer

### 2. Agregar tipo "summarizer" a phones.json (empresa de prueba)

Leer primero la estructura de phones.json para no romper nada. Agregar a algún contacto:
```json
"tools": [{"type": "summarizer"}]
```

### 3. Tests

Crear `backend/tests/test_summarizer.py`:
- Acumular texto → verificar estructura del .md
- Acumular varios mensajes → verificar append correcto
- Endpoint GET devuelve el documento

```bash
cd backend && pytest tests/test_summarizer.py -v
```

### 4. Agregar `data/summaries/` al .gitignore
```bash
echo "data/summaries/" >> .gitignore
```

### 5. Fase 2 — Transcripción de audios (avanzar todo lo posible)

**Instalar dependencias:**
```bash
cd backend && .venv/bin/pip install groq pywhispercpp
```
Si `pywhispercpp` falla, continuar igual — el código maneja `ImportError`.

**Crear `backend/tools/transcription.py`:**
```python
import os, logging
logger = logging.getLogger(__name__)

async def transcribe(audio_path: str) -> str:
    try:
        return await _transcribe_groq(audio_path)
    except Exception as e:
        logger.warning(f"Groq falló ({e}), usando fallback local")
        return _transcribe_local(audio_path)

async def _transcribe_groq(audio_path: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3", file=f, language="es"
        )
    return result.text

def _transcribe_local(audio_path: str) -> str:
    try:
        from pywhispercpp.model import Model
        model = Model("small", n_threads=4)
        segments = model.transcribe(audio_path)
        return " ".join([s.text for s in segments])
    except ImportError:
        return "[audio sin transcribir — configurar GROQ_API_KEY o instalar pywhispercpp]"
```

**Detectar audios en `sim.py`:**
- Agregar soporte para `msg_type: "audio"` en el simulador con campo `audio_path`
- Cuando llega audio: llamar `transcribe()` → pasar texto a `summarizer.accumulate()`

**Detectar audios en `whatsapp.py`:**
- En `_on_message`, si `message.type == 'audio'` o tiene media
- Descargar a `/tmp/pulpo_audio_{timestamp}.ogg`
- Llamar `transcribe()` → pasar a `summarizer.accumulate()`
- Si la descarga de media con Playwright es muy compleja, dejar `TODO` claro y mergear sin ella.
  Se termina en master donde hay sesión WA real para probar.

---

## Lo que NO hacer en el worktree

- No tocar `data/sessions/` ni procesos WA reales
- No hacer push a origin (lo hace la sesión de `_`)
- No cambiar schema de DB si se puede evitar
- No romper el flujo de tools existentes (la sumarizadora es aditiva)

---

## Estado al 2026-03-19

### ✅ Fase 1 completa
- `backend/tools/summarizer.py` — accumulate / get_summary / list_contacts
- `backend/api/summarizer.py` — GET /api/summarizer/{empresa_id} + GET /api/summarizer/{empresa_id}/{contact_phone}
- `backend/db.py` — CHECK constraint actualizado + migración automática para tablas existentes
- `backend/api/tools.py` — tipo 'summarizer' permitido en create/update
- `backend/sim.py` — pipeline no-blocking: accumulate ANTES de resolver tool de respuesta
- `backend/main.py` — router summarizer registrado
- `.gitignore` — data/summaries/ ignorado
- `backend/tests/test_summarizer.py` — 9 tests, todos verdes
- Frontend `EmpresaPage.jsx`:
  - Select con opción "Sumarizadora (pasiva)"
  - Tabla muestra tipo correcto
  - Botón "Ver resúmenes" abre modal con lista de contactos + contenido del .md

### 🔧 Fase 2 pendiente (para master con sesión WA real)
- `backend/tools/transcription.py` — Groq + pywhispercpp fallback (código en NEXT_SESSION.md arriba)
- Detectar audios en `sim.py` (msg_type: "audio" con audio_path)
- Detectar audios en `whatsapp.py` (message.type == 'audio', descargar media)

### Para mergear
- Todo está en orden, sin tests rojos nuevos
- Los 21 fallos pre-existentes son por ADMIN_PASSWORD=MonoLoco vs hardcoded "admin" en test fixtures — pre-existentes, no introducidos por este feature
