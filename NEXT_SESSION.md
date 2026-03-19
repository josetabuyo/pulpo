# NEXT SESSION — transcripcion-audio

## Contexto
Worktree de desarrollo para la **Fase 2 de la tool sumarizadora**: transcripción de mensajes de audio de WhatsApp.

La Fase 1 (acumulación de texto) está completa y en producción. Este worktree agrega:
1. ✅ `backend/tools/transcription.py` — transcribir audios con Groq API (fallback: pywhispercpp local)
2. ✅ Detectar audios en `whatsapp.py` y acumular con tipo "audio" (placeholder mientras descarga Playwright es compleja)
3. ✅ Detectar audios en `sim.py` — `sim_receive(audio_path=...)` + endpoint `POST /api/sim/send-audio/{number}`
4. ✅ Tests: 14 tests verdes en `test_summarizer.py`

## Estado: **LISTO PARA MERGE**

## Puertos
- Backend: `:8001` | Frontend: `:5174` | `ENABLE_BOTS=false`

## Arrancar
```bash
cd /Users/josetabuyo/Development/pulpo/transcripcion-audio
./start.sh
```

---

## Orden de trabajo — modo dangerous

### 1. Instalar dependencias
```bash
cd backend
.venv/bin/pip install groq
.venv/bin/pip install pywhispercpp  # puede fallar en Apple Silicon — OK, es fallback
```

### 2. Crear `backend/tools/transcription.py`
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
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no configurada")
    client = Groq(api_key=api_key)
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

### 3. Integrar en `sim.py`
- Agregar `audio_path: str | None = None` a `sim_receive`
- Si hay audio y summarizers: `transcription.transcribe(audio_path)` → `accumulate(msg_type="audio")`
- Agregar `POST /api/sim/send-audio` que acepta `{session_id, from_name, from_phone, audio_path}`

### 4. Integrar en `whatsapp.py`
En `_on_message`, detectar mensajes de audio del scraper JS y:
- Descargar el blob a `/tmp/pulpo_audio_{timestamp}.ogg` via Playwright
- Llamar `transcription.transcribe(path)` → `summarizer.accumulate(..., msg_type="audio")`
- Si la descarga es muy compleja con Playwright: registrar como `[audio — pendiente transcripción]` y dejar TODO claro

### 5. Tests
- `test_summarizer.py`: test de sim_receive con audio_path y test del fallback sin GROQ_API_KEY

---

## Lo que NO hacer
- No tocar `data/sessions/` (ENABLE_BOTS=false)
- No hacer push a origin (lo hace la sesión de `_`)
- No cambiar schema de DB

## Merge
Cuando esté listo, avisarle a la sesión de `_` para merge + push.
