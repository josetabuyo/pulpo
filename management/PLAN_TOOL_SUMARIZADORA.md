# Plan: Tool Sumarizadora — Acumulación de información de conversaciones

## Objetivo

Crear una nueva tool que, cuando se asigna a un contacto, escucha silenciosamente la conversación y acumula todo el contenido en un documento Markdown estructurado. Los mensajes de texto se vuelcan tal como llegan. Los audios se descargan y transcriben a texto. El resultado es un archivo `.md` por contacto que crece con el tiempo y puede leerse como un log rico.

**Mínimo viable:** log acumulativo de texto plano volcado a Markdown, con timestamps.
**Nice to have:** procesamiento con IA para redactar un informe ordenado y cohesivo.

---

## Caso de uso

Un operador quiere hacer seguimiento de lo que habla con un contacto a lo largo del tiempo. Activa la tool sumarizadora para ese contacto. A partir de ahí, todo lo que el contacto diga (texto o audio) queda registrado en un documento acumulativo. El operador puede abrir ese documento en cualquier momento y leer el historial completo, incluyendo las transcripciones de los audios.

---

## Análisis técnico

### ¿Qué es una "tool" en Pulpo?

Las tools son handlers que se activan por contacto y empresa. Cuando llega un mensaje de un contacto que tiene una tool asignada, el sistema llama a `resolve_tool` → ejecuta la lógica de la tool → puede responder automáticamente o solo registrar.

La tool sumarizadora es **pasiva**: no responde al contacto, solo registra.

### Tipos de mensaje a manejar

| Tipo | Formato WhatsApp | Acción |
|------|-----------------|--------|
| Texto | string | Volcar directo al MD |
| Audio/voz | `.ogg` (opus codec) | Descargar → transcribir → volcar texto al MD |
| Imagen | `.jpg/.png` | (futuro) OCR o descripción |
| Documento | `.pdf/.docx` | (futuro) |

**Fase 1 solo maneja texto y audio.**

### Dónde se guardan los documentos

```
data/summaries/{empresa_id}/{contacto_phone}.md
```

Cada contacto tiene su propio archivo. El archivo crece append-only — nunca se sobreescribe, siempre se agrega al final.

### Estructura del documento acumulado

```markdown
# Resumen: +54911xxxxxxx (Ivancho)
**Empresa:** gm_herreria
**Inicio:** 2026-03-18

---

## 2026-03-18 14:32

**[texto]** Hola, quería consultar por los precios del hierro cuadrado 3/8

---

## 2026-03-18 14:35

**[audio 0:42]** _transcripción:_ Mirá lo que pasa es que necesito unas 20 barras para un proyecto que tenemos, la semana que viene si puede ser, y quería saber si tienen stock disponible porque la última vez que vine no había

---

## 2026-03-18 14:41

**[texto]** Perfecto, te mando la dirección por acá
```

---

## Investigación: Transcripción de audio

### Recomendación: Groq API (primario) + whisper.cpp small (fallback)

**Groq API — opción principal:**
- Free tier: **8 horas de audio por día** (recurrente, no se agota)
- Modelo: `whisper-large-v3` — calidad excelente en español (incluyendo acentos regionales)
- Velocidad: ~1 segundo por mensaje de 30 segundos
- Setup: `pip install groq`, API key, 5 líneas de código
- Acepta `.ogg` opus directamente (formato nativo de WhatsApp)
- Sin consumo de RAM del servidor, sin modelos locales

**whisper.cpp — fallback offline:**
- Corre local, sin internet, permanentemente gratuito
- En Mac usa Metal (GPU Apple Silicon) → 3-5x más rápido que la versión Python
- Modelo `small`: 466 MB disco, ~852 MB RAM, buena calidad en español
- Se llama desde Python vía subprocess o `pywhispercpp`

**Estrategia:** intentar Groq primero → si falla (timeout, rate limit, sin internet) → fallback a whisper.cpp local.

**Lo que se descartó y por qué:**
- Whisper Python (tiny/base): calidad en español demasiado baja
- Google STT: solo 60 min/mes gratuitos
- AssemblyAI / Deepgram: créditos que se agotan, no recurrentes
- faster-whisper: en Mac no usa Metal, pierde frente a whisper.cpp

---

## Arquitectura de implementación

### Fase 1 — Tool pasiva, solo texto (MVP rápido)

1. **Nuevo tipo de tool:** `summarizer` en la DB / phones.json
2. **`resolve_tool`:** cuando detecta tipo `summarizer`, en vez de buscar respuesta, llama a `tool_summarizer.accumulate(empresa_id, contact_phone, message)`
3. **`tool_summarizer.py`:** módulo nuevo en `backend/tools/`
   - `accumulate(empresa_id, contact_phone, msg_type, content, timestamp)` → append al `.md`
   - `get_summary(empresa_id, contact_phone)` → retorna el contenido del `.md`
4. **Endpoint API:** `GET /api/tools/summarizer/{empresa_id}/{contact}` → devuelve el documento
5. **UI mínima:** botón "Ver resumen" en el portal de empresa para contactos con esta tool activa

### Fase 2 — Descarga y transcripción de audios

1. **Detectar mensajes de audio:** en `whatsapp.py` y `sim.py`, cuando `message.type == 'audio'`
2. **Descargar el audio:** Playwright puede acceder al blob URL del audio en WA Web
   - Alternativa: usar la API de descarga de medios de WA si está disponible
3. **Transcribir:**
   ```python
   async def transcribe_audio(audio_path: str) -> str:
       try:
           return await transcribe_groq(audio_path)
       except Exception:
           return transcribe_whisper_cpp(audio_path)  # fallback
   ```
4. **Pasar la transcripción** al acumulador como tipo `audio` con texto

### Fase 3 — Procesamiento con IA (informe elaborado)

1. **Trigger manual:** endpoint `POST /api/tools/summarizer/{empresa_id}/{contact}/process`
2. **Prompt al LLM (Claude API o Groq):** tomar el log acumulado + prompt de síntesis
   ```
   Sos un asistente que analiza conversaciones de clientes.
   Dado este log de conversación, generá un informe estructurado con:
   - Resumen ejecutivo (2-3 oraciones)
   - Temas principales discutidos
   - Compromisos o acuerdos mencionados
   - Pendientes o seguimientos requeridos
   ```
3. **Guardar el informe** en `data/summaries/{empresa_id}/{contact}_informe.md`
4. **UI:** botón "Generar informe" junto al botón "Ver resumen"

---

## Archivos a crear/modificar

### Nuevos
```
backend/tools/summarizer.py        — lógica de acumulación + transcripción
backend/tools/transcription.py     — wrapper Groq + fallback whisper.cpp
backend/api/summarizer.py          — router: GET/POST endpoints
data/summaries/                    — directorio de documentos (gitignoreado)
```

### Modificar
```
backend/main.py                    — registrar router summarizer
backend/sim.py                     — pasar mensaje a summarizer si tool activa
backend/automation/whatsapp.py     — idem, más descarga de audio
backend/db.py                      — si se necesita persistir estado en DB
frontend/src/                      — botón "Ver resumen" en portal empresa
```

---

## Dependencias nuevas

```
groq                   # pip install groq — cliente Groq API
pywhispercpp           # pip install pywhispercpp — binding Python para whisper.cpp (fallback)
ffmpeg                 # brew install ffmpeg — para convertir formatos de audio
```

Variables de entorno nuevas en `.env`:
```
GROQ_API_KEY=...       # obtener gratis en console.groq.com
```

---

## Tests

### Backend
- `tests/test_summarizer.py`:
  - Acumular mensajes de texto → verificar estructura del `.md`
  - Acumular mensaje de audio (mock transcripción) → verificar que aparece el texto
  - Endpoint GET devuelve el documento correcto
  - Endpoint de múltiples contactos no mezcla documentos

### Simulador
- Agregar tipo de mensaje `audio` al simulador con campo `audio_url` o `audio_path`
- El sim debe poder correr sin Groq key (transcripción mockeada en tests)

---

## Estado

- [ ] Fase 1 — Tool pasiva acumula texto, endpoint API, UI mínima
- [ ] Fase 2 — Descarga y transcripción de audios (Groq + fallback whisper.cpp)
- [ ] Fase 3 — Procesamiento IA para informe elaborado
- [ ] Fase 4 — Tests completos

---

## Notas de diseño

- El acumulador es **append-only**: nunca borra ni reescribe, solo agrega. Esto garantiza que no se pierde información.
- La tool sumarizadora **no responde** al contacto. Es invisible para el interlocutor.
- Un contacto puede tener la tool sumarizadora Y otra tool de respuesta automática activa al mismo tiempo (no son exclusivas).
- El directorio `data/summaries/` va en `.gitignore` — es información sensible de clientes.
- En Fase 1 se puede activar la tool sin tener Groq API key configurada; simplemente los audios aparecerán marcados como `[audio sin transcribir]` hasta que se configure.
