# Feature: Imágenes en el Summarizer

## Estado
- **Planificado** — pendiente de worktree
- **Prioridad**: media (audio y documentos ya funcionan; imágenes son el gap restante)

## Diagnóstico actual

El pipeline de summarizer soporta exactamente tres tipos de mensaje:

| Tipo | Listener (tiempo real) | Full-sync |
|------|----------------------|-----------|
| `text` | ✅ `pollOpenChat` + sidebar | ✅ `_extract_text_msgs_js` |
| `audio` | ✅ detectado por markers (🎵, 🎤, duración) → transcripción | ✅ `_extract_audio_msgs_js` |
| `document` | ✅ detectado por `[doc:...]` inyectado por JS | ✅ `_extract_document_msgs_js` |
| **`image`** | ❌ silently ignored | ❌ no existe |

**¿Qué pasa hoy con una imagen?**
- Imagen SIN caption: `body` vacío en `pollOpenChat` → `if (!body) return;` → ignorada
- Imagen CON caption: el texto de la caption se captura como `msg_type="text"` (el extractor de texto sí ve `data-pre-plain-text`)
- En full-sync: la imagen nunca aparece en `raw_msgs_text | raw_msgs_audio | raw_msgs_docs`

## DOM de WA Web — lo que sabemos

### Chat abierto (`msg-container`)

WA Web usa `[data-testid="msg-container"]` para cada mensaje en el panel.

Para **imágenes**:
- El contenedor tiene un `img[src^="blob:"]` como elemento hijo (preview thumbnail)
- El `img` puede tener un `aria-label` como "Foto" o similar
- Si hay caption: aparece debajo como `span.copyable-text` (ya capturado por text extractor)
- El mensaje de imagen SIN `data-pre-plain-text` → mismo patrón que audio/document
- El blob de la imagen es accesible via `fetch(img.src)` cuando ya está cargado

Selector candidato para detectar imagen en `pollOpenChat`:
```javascript
const imgEl = lastMsg.querySelector('img[src^="blob:"]');
// Excluir avatares y thumbnails de sidebar
// WA Web: las imágenes de mensaje están dentro de un div con clase específica
// o con aria-label como "Foto" / "Photo"
const imgEl = lastMsg.querySelector('img[src^="blob:"][alt], img[aria-label*="Foto"], img[aria-label*="Photo"]');
```

### Full-sync (historial)

Selector candidato para `_extract_image_msgs_js`:
```javascript
// Mensajes de imagen sin data-pre-plain-text (caption vacía)
// Las imágenes aparecen en contenedores .message-in / .message-out
// con un img[src^="blob:"] o con un div que tiene el thumbnail
const imgContainers = [...document.querySelectorAll('.message-in, .message-out')]
  .filter(m => !m.querySelector('[data-pre-plain-text]') && m.querySelector('img[src^="blob:"]'));
```

**⚠️ A confirmar inspeccionando DOM real**: WA Web cambia clases frecuentemente.
La sesión de worktree debe hacer inspección manual primero (`browser_evaluate` para listar elementos).

## Arquitectura de la solución

### 4 cambios en `backend/automation/whatsapp.py`

#### Cambio 1: `pollOpenChat()` — detectar imagen en chat abierto (línea ~534)

Después del bloque de documento, agregar:
```javascript
// Si body vacío, verificar si es una imagen
if (!body) {
    const imgEl = lastMsg.querySelector('img[src^="blob:"]');
    if (imgEl) {
        body = '[img:]';  // placeholder; el download se hace en Python
    }
}
```

#### Cambio 2: `_on_message` — rama de imagen (línea ~307)

```python
_is_image = body == '[img:]'

# En el loop de summarizers:
elif _is_image:
    img_path = await self._download_image_blob(page, name, session_id)
    if img_path:
        summarizer_mod.accumulate(
            empresa_id=s_tool["empresa_id"],
            contact_phone=sender,
            contact_name=name,
            msg_type="image",
            content=_group_content(f"[imagen guardada: {img_path.name}]"),
            timestamp=_acc_ts,
        )
    else:
        summarizer_mod.accumulate(
            empresa_id=s_tool["empresa_id"],
            contact_phone=sender,
            contact_name=name,
            msg_type="image",
            content=_group_content("[imagen — no disponible]"),
            timestamp=_acc_ts,
        )
```

#### Cambio 3: `_download_image_blob()` — nuevo método (similar a `_download_audio_blob`, línea ~845)

```python
async def _download_image_blob(
    self, page, sender_name: str, session_id: str
) -> Path | None:
    """
    Localiza el último mensaje de imagen en el chat abierto,
    descarga el blob y guarda en data/attachments/{session_id}/{sender}/img_{ts}.jpg.
    Retorna el Path del archivo, o None si falla.
    """
    import base64 as _b64
    import time
    try:
        blob_b64 = await page.evaluate("""
        async () => {
            const msgs = document.querySelectorAll('[data-testid="msg-container"]');
            for (let i = msgs.length - 1; i >= 0; i--) {
                const img = msgs[i].querySelector('img[src^="blob:"]');
                if (!img) continue;
                try {
                    const resp = await fetch(img.src);
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let bin = '';
                    for (let b of bytes) bin += String.fromCharCode(b);
                    return btoa(bin);
                } catch(e) { return null; }
            }
            return null;
        }
        """)
        if not blob_b64:
            return None
        # Guardar en attachments del summarizer
        # TODO: usar get_attachments_dir del summarizer module
        path = Path(f"/tmp/pulpo_img_{int(time.time()*1000)}.jpg")
        path.write_bytes(_b64.b64decode(blob_b64))
        return path
    except Exception as e:
        logger.warning(f"[{session_id}] _download_image_blob error: {e}")
        return None
```

#### Cambio 4: `_extract_image_msgs_js()` — extractor para full-sync (línea ~1607)

```python
def _extract_image_msgs_js():
    """Busca mensajes de imagen sin data-pre-plain-text (sin caption).
    Selector a confirmar inspeccionando DOM real de WA Web.
    """
    return """
    () => {
        const msgs = [];
        const seen = new Set();
        // Imágenes sin caption: no tienen data-pre-plain-text
        const candidates = [...document.querySelectorAll('.message-in, .message-out')]
            .filter(m => !m.querySelector('[data-pre-plain-text]') && m.querySelector('img[src^="blob:"]'));
        for (const msgContainer of candidates) {
            // Timestamp (mismo patrón que audio/document)
            let msgTime = '';
            const walker = document.createTreeWalker(msgContainer, NodeFilter.SHOW_TEXT, null);
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (/^\\d{1,2}:\\d{2}(\\s*(a|p)[\\.\\s]*m\\.?)?$/i.test(t)) msgTime = t;
            }
            if (!msgTime) continue;
            // Fecha: último data-pre-plain-text antes de esta imagen
            let msgDate = '';
            for (const el of document.querySelectorAll('[data-pre-plain-text]')) {
                if (!(msgContainer.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) break;
                const m = el.getAttribute('data-pre-plain-text').match(/(\\d{1,2}\\/\\d{1,2}\\/\\d{4})/);
                if (m) msgDate = m[1];
            }
            const timeText = msgTime && msgDate ? msgTime + ', ' + msgDate : msgTime;
            if (!timeText) continue;
            const isOut = msgContainer.classList.contains('message-out');
            const prePlain = '[' + timeText + '] ';
            const key = prePlain + '|img';
            if (seen.has(key)) continue;
            seen.add(key);
            msgs.push({ source: 'image', idx: -1, prePlain, body: '[imagen]', isOut, msg_type: 'image' });
        }
        return msgs;
    }
    """
```

Y en `scrape_full_history`, agregar `raw_msgs_images` al merge (línea ~1737):
```python
raw_msgs_images = await page.evaluate(_extract_image_msgs_js())
raw_msgs = raw_msgs_text + raw_msgs_audio + raw_msgs_docs + raw_msgs_images
```

## Almacenamiento de imágenes

Las imágenes descargadas van a `data/summaries/{empresa_id}/attachments/{phone}/img_{ts}.jpg`.

`summarizer.py` ya tiene `get_attachments_dir()` — confirmar que funciona para imágenes también.

En el `.md` del contacto, la imagen queda como:
```markdown
## 2026-03-22 14:30
**[image]** [imagen guardada: img_1742654800000.jpg]
---
```

## Plan de trabajo en worktree

1. **Crear worktree** desde `_`:
   ```bash
   git worktree add /Users/josetabuyo/Development/pulpo/feat-img-scraping -b feat-img-scraping
   ```

2. **Inspeccionar DOM real**: con `ENABLE_BOTS=false` + simulador, enviar una imagen al bot desde otro teléfono real, o usar WA Web directamente para inspeccionar un chat con imagen reciente.

3. **Confirmar selectores**: ejecutar en browser console de WA Web:
   ```javascript
   [...document.querySelectorAll('[data-testid="msg-container"]')]
     .filter(m => m.querySelector('img[src^="blob:"]'))
     .map(m => ({
       hasPrePlain: !!m.querySelector('[data-pre-plain-text]'),
       imgAlt: m.querySelector('img[src^="blob:"]')?.alt,
       imgAria: m.querySelector('img[src^="blob:"]')?.getAttribute('aria-label'),
       outerHTMLSnip: m.outerHTML.slice(0, 300)
     }))
   ```

4. **Implementar** los 4 cambios listados arriba, ajustando selectores según DOM real.

5. **Test**: enviar imagen desde teléfono real al bot en modo simulado/dev → verificar que aparece en `.md`.

6. **Merge desde `_`** cuando tests pasen.

## Riesgos

- WA Web puede cambiar sus clases CSS sin aviso → los selectores basados en `img[src^="blob:"]` son más estables que los basados en clases
- Los blob URLs de imágenes pueden expirar antes de que el fetch los descargue → probar con timeout
- Imágenes sin caption podrían tener `data-pre-plain-text` en el contenedor padre → riesgo de duplicados con el text extractor (el text extractor ya filtra por `body || '[media]'`)
