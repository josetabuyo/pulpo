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
| Documento | `.pdf/.docx/.sql/.pptx/etc.` | Mínimo: mencionar en MD. Máximo: descargar. Ver spec abajo. |
| Imagen | `.jpg/.png` | (futuro) OCR o descripción |

**Fase 1 maneja texto, audio y documentos (mención). Fase 2 suma transcripción de audio. Fase 3 descarga de documentos.**

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

---

## 2026-03-20 16:59

**[documento]** `Agregar Módulo en menú principal.sql` (SQL · 3 kB) — Fabian Miranda

---

## 2026-03-21 08:47

**[documento]** `Pantallas Telefono y Mails en Datos Personales de la Web.pptx` (PPTX · 300 kB) — Fabian Miranda
```

---

## Spec: Mensajes de documento en WA Web

### Hallazgo DOM (inspeccionado 2026-03-21 con MCP en conversación real)

Los mensajes de documento **NO tienen `data-pre-plain-text`** — son invisibles para el extractor actual (Part A y Part B en `whatsapp.py`). Quedan completamente perdidos.

**Estructura del nodo en el DOM:**

```
.message-in / .message-out
  └── div[role="button"][tabindex="0"][title='Descargar "filename.ext"']
        innerText: "SQL\nAgregar Módulo en menú principal.sql\nSQL•3 kB"
        innerText: "P\nPantallas Telefono y Mails en Datos Personales de la Web.pptx\nPPTX•300 kB"
```

- `title` del botón: `Descargar "nombre-del-archivo.ext"` → filename completo
- `innerText` del botón: `TIPO\nnombre-del-archivo.ext\nTIPO•TAMAÑO`
- El SVG tiene `data-icon="document-SQL-icon"`, `data-icon="document-P-icon"`, etc.
- No hay `data-pre-plain-text` ni en el elemento ni en sus ancestros

**Selector confiable:**
```js
div[role="button"][title^="Descargar"]
```

**Extracción de metadata:**
```js
const title = docBtn.title;  // 'Descargar "archivo.sql"'
const filename = title.replace(/^Descargar\s*"?/, '').replace(/"$/, '');
// innerText = "SQL\narchivo.sql\nSQL•3 kB"
const parts = docBtn.innerText.split('\n');
const sizeLine = parts[2] || '';  // "SQL•3 kB"
const size = sizeLine.split('•')[1]?.trim() || '';  // "3 kB"
const ext = filename.split('.').pop().toUpperCase();  // "SQL"
```

---

### Implementación mínima: mencionar el archivo en el resumen

**Qué se registra en el `.md`:**
```markdown
## 2026-03-20 16:59
**[documento]** `Agregar Módulo en menú principal.sql` (SQL · 3 kB) — Fabian Miranda
```

**Dónde implementar:** `_extract_text_msgs_js` en `whatsapp.py` ya tiene Part A (texto) y Part B (audio). Hay que agregar **Part C — documentos**:

```python
def _extract_document_msgs_js():
    """Busca mensajes de documento que NO usan data-pre-plain-text.
    Selector confirmado inspeccionando DOM real de WA Web: div[role="button"][title^="Descargar"]
    """
    return """
    () => {
        const msgs = [];
        const seen = new Set();
        for (const docBtn of document.querySelectorAll('div[role="button"][title^="Descargar"]')) {
            // Subir al contenedor de mensaje
            let msgContainer = docBtn;
            for (let i = 0; i < 15; i++) {
                if (!msgContainer.parentElement) break;
                msgContainer = msgContainer.parentElement;
                if (msgContainer.classList.contains('message-in') ||
                    msgContainer.classList.contains('message-out')) break;
            }

            // Extraer filename y tamaño
            const titleAttr = docBtn.title;  // 'Descargar "archivo.ext"'
            const filename = titleAttr.replace(/^Descargar\\s*"?/, '').replace(/"$/, '').trim();
            const innerParts = (docBtn.innerText || '').split('\\n');
            const sizeLine = innerParts[2] || '';
            const size = sizeLine.split('•')[1]?.trim() || '';

            // Timestamp — mismo algoritmo que Part B
            let msgTime = '';
            const walker = document.createTreeWalker(msgContainer, NodeFilter.SHOW_TEXT, null);
            let node2;
            while (node2 = walker.nextNode()) {
                const t = node2.textContent.trim();
                if (/^\\d{1,2}:\\d{2}(\\s*(a|p)[\\.]?\\s*m\\.?)?$/i.test(t)) msgTime = t;
            }

            // Sender — span con color (grupos) o texto visible más cercano
            const senderEl = msgContainer.querySelector('span[style*="color:#"], span[style*="color: #"]');
            const sender = senderEl ? senderEl.innerText.trim() : '';

            // Fecha — usar separador de día WA (igual a Part B)
            // [Mismo bloque de resolución de fecha que Part B — reutilizar función helper]
            const isOut = msgContainer.classList.contains('message-out');

            if (!msgTime) continue;
            const key = msgTime + '|' + sender + '|' + filename;
            if (seen.has(key)) continue;
            seen.add(key);

            msgs.push({ source: 'document', filename, size, sender, msgTime, isOut });
        }
        return msgs;
    }
    """
```

En el acumulador, el formato en el MD:
```python
if msg['msg_type'] == 'document':
    label = f"[documento] `{msg['filename']}`"
    if msg.get('size'):
        label += f" ({msg['size']})"
    body = label
```

---

### Implementación máxima: descargar el archivo

**Opción A — Click en el botón de descarga vía Playwright:**
- Playwright hace `.click()` en `div[role="button"][title^="Descargar ..."}`
- WA Web descarga el archivo al directorio de descargas del perfil Chrome
- Problema: el directorio de descarga por defecto varía, y el timing es incierto

**Opción B — Interceptar descarga con Playwright:**
```python
async with page.expect_download() as download_info:
    await page.click(f'div[role="button"][title="Descargar \\"{filename}\\""]')
download = await download_info.value
await download.save_as(f"data/summaries/{empresa_id}/docs/{filename}")
```
- Esta API de Playwright maneja el timing automáticamente
- Requiere que el botón sea clickeable (el mensaje debe estar visible en el DOM)
- Limitación: solo funciona en el momento que llega el mensaje (durante el listener activo), no en full-sync histórico

**Opción C — IndexedDB (misma técnica que audios PTT):**
- WA Web cachea todos los medios en IndexedDB
- Se puede recuperar el blob por `mediaKey` o `directPath` del mensaje
- Más robusto que el click, funciona también en full-sync histórico
- Requiere el mismo tipo de investigación DOM que se hizo para audios

**Recomendación para Fase 3:** usar Opción B (Playwright download) para mensajes recibidos en tiempo real. Opción C para full-sync histórico.

**Destino de archivos descargados:**
```
data/summaries/{empresa_id}/docs/{contact_phone}/{filename}
```

**Qué registra en el MD cuando hay descarga:**
```markdown
## 2026-03-20 16:59
**[documento]** `Agregar Módulo en menú principal.sql` (SQL · 3 kB) — descargado en `docs/5491155612767/Agregar Módulo en menú principal.sql`
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

- [x] Fase 1 — Tool pasiva acumula texto + documentos (mención), endpoint API, UI mínima
  - [x] Part A: mensajes de texto (ya implementado en whatsapp.py)
  - [x] Part C nueva: documentos — `_extract_document_msgs_js()` en `whatsapp.py` (2026-03-21)
  - [x] Real-time: `pollOpenChat` JS detecta `div[role="button"][title^="Descargar"]` → `[doc:filename|EXT·size]`
  - [x] Real-time Python: detecta `[doc:` prefix → `accumulate(msg_type="document")`
  - [x] Acumulador `tool_summarizer.py` con soporte para msg_type=`document` (ya funciona por diseño)
  - [x] Endpoint GET para ver el MD (ya existía)
  - [x] Botón "Ver resúmenes" en EmpresaPage (ya existía)
- [x] Fase 2 — Descarga y transcripción de audios (Groq + fallback whisper.cpp) — implementado en whatsapp.py (tiempo real + full-sync IDB/DOM) y telegram_bot.py
- [x] Fase 3 — Descarga de documentos adjuntos — implementado con `_download_document_from_page` (expect_download) en tiempo real y en full-sync histórico
- [ ] Fase 4 — Procesamiento IA para informe elaborado
- [ ] Fase 5 — Tests completos

---

## Notas de diseño

- El acumulador es **append-only**: nunca borra ni reescribe, solo agrega. Esto garantiza que no se pierde información.
- La tool sumarizadora **no responde** al contacto. Es invisible para el interlocutor.
- Un contacto puede tener la tool sumarizadora Y otra tool de respuesta automática activa al mismo tiempo (no son exclusivas).
- El directorio `data/summaries/` va en `.gitignore` — es información sensible de clientes.
- En Fase 1 se puede activar la tool sin tener Groq API key configurada; simplemente los audios aparecerán marcados como `[audio sin transcribir]` hasta que se configure.
