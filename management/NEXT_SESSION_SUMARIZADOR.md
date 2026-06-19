# HANDOFF — Sumarizador / Scraper WA
**Fecha:** 2026-05-14  
**Commit actual:** `cc0ba25`  
**Tests:** 66 unitarios pasando (`test_auth`, `test_logs`, `test_sim`, `test_delta_sync`, `test_whatsapp_sync`)

---

## TL;DR para la próxima sesión

Se hizo un import completo (full-resync + backup previo) de un contacto de garantido.
Hay **dos bugs visibles en la UI** después del import:

1. **Audios sin transcripción** — algunos mensajes de audio muestran solo el ícono `🎵` sin texto, cuando deberían tener transcripción.
2. **Mensaje visualmente desacomodado** — un mensaje que antes aparecía en la posición correcta ahora aparece en lugar incorrecto. Probablemente ordering issue dentro del mismo minuto (`.md` guarda timestamps con precisión de **minutos**, no segundos).

---

## Lo que se completó en esta sesión (2026-05-14)

### Refactor arquitectónico completo — 6 fases

| Fase | Descripción | Commit |
|------|-------------|--------|
| 1 | TDD: 23 tests definen contrato de `automation/sync.py` | `21fd439` |
| 2 | `automation/sync.py`: `delta_sync` + `StopCondition` enum | `95e9104` |
| 3 | Migración: `_do_import` (flows.py) + `full_resync_contact` (summarizer.py) usan `delta_sync` | `95e9104` |
| 4 | Docs: `_poll_sidebar_for_delta` documenta semántica UNTIL_KNOWN | `cc0ba25` |
| 5 | UI: `BrowserPanel` siempre visible, TV noise cuando browser cerrado | `e642b7f` |
| 6 | Docs: `sync_contact` / `sync_all_contacts` marcados "FUENTE: DB (no WA Web)" | `cc0ba25` |

### Alineación derecha mensajes salientes
- `_parse_messages` detecta owner_names (Jozbuyo, Tú) → `direction: "out"`
- `SummaryView.jsx`: burbujas `--out` alineadas a la derecha en todos los tipos (text, audio, image)
- `connections.json` (local): `"owner_name": "Jozbuyo"` agregado a las entradas de `la_piquiteria` y `garantido`

---

## Bug 1 — Audios sin transcripción

### Síntoma
`AudioBubble` muestra `🎵 audio` sin botón "Transcripción". El `.md` tiene la entrada de audio pero sin texto transcripto.

### Posible causa
El scraper descargó el audio como archivo temporal durante el import, pero el pipeline de transcripción no lo procesó. Los audios se guardan en `data/summaries/{bot}/{contact}/docs/` pero la transcripción (que normalmente corre durante el real-time scrape) puede haberse saltado en el batch import.

### Dónde investigar
- `backend/automation/whatsapp.py` — `_download_audio_from_page()` y cómo el resultado se pasa al pipeline
- `backend/api/flows.py` — `_do_import()` → `delta_sync()` → ¿se transcribe el audio en el momento del scrape o solo se guarda el blob?
- El `.md` del contacto: buscar entradas `[audio — sin blob]` o `[audio — error]`
- Test existente relevante: `backend/tests/test_audio_transcription.py` (si existe)

### Comandos para diagnosticar
```bash
# Ver entradas de audio en el chat.md
grep -n "\[audio" data/summaries/garantido/andres-buxareo/chat.md | head -20

# Contar audios con placeholder (sin transcripción real)
grep -c "\[audio" data/summaries/garantido/andres-buxareo/chat.md

# Ver si hay blobs descargados
ls data/summaries/garantido/andres-buxareo/docs/
```

---

## Bug 2 — Mensaje desacomodado (timestamp ordering)

### Síntoma
Un mensaje que aparecía en la posición cronológica correcta antes ahora aparece fuera de lugar.

### Causa raíz probable
`accumulate()` en `graphs/nodes/summarize.py` línea 205 guarda timestamps con precisión de **minutos**:
```python
ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M")  # sin segundos
```

El `.md` queda con `## 2026-05-13 10:45` sin segundos. Cuando `get_messages` en `summarizer.py` mezcla:
- mensajes del `.md` (timestamps a minutos)
- respuestas del bot de la DB (timestamps con segundos)

...y los ordena con `sorted(..., key=lambda m: m.get("timestamp") or "")`, dos mensajes del mismo minuto pueden quedar en orden incorrecto si el scraper los capturó en 10:45:55 pero el `.md` los guarda como 10:45.

### Investigar
1. ¿El mensaje desacomodado es del mismo minuto que otro mensaje?
2. ¿Estaba el mensaje mal ordenado en el `.md` antes de la última sesión (es decir, siempre fue así)?
3. ¿O se introdujo en esta sesión?

### Fix posible
Agregar segundos al formato de `accumulate`:
```python
ts = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")  # con segundos
```
Y actualizar `_parse_messages` para aceptar ambos formatos al leer el `.md`.
**Riesgo:** cambia el formato del `.md` → dedup y lookup por timestamp necesitan adaptarse.

---

## Arquitectura vigente — 4 caminos de recolección

```
Camino 1 — Real-time (sidebar scanner)
  _poll_sidebar_for_delta → _run_delta_sync → scrape WA Web (UNTIL_KNOWN)
  → DB (log_message_historic) + run_flows → SummarizeNode → accumulate → .md

Camino 2 — DB sync (botón ↻ en SummaryView)
  /summarizer/{eid}/{phone}/sync → FUENTE: DB (no WA Web, solo entrantes)
  → accumulate → .md

Camino 3 — Import scraper (UI o API)
  /import-wa-history → delta_sync(FULL_ENRICH) → accumulate → .md
  (archivos adjuntos en doc_save_dir)

Camino 4 — Full resync (botón "⟳ Full" en SummaryView)
  /full-resync → clear_contact_full + delta_sync(FULL_ENRICH) → accumulate → .md
```

**Nota importante:** `sync_contact` (Camino 2) solo incluye mensajes entrantes (`outbound=0`).
Para ver mensajes salientes del dueño del teléfono en la UI, es necesario hacer un scrape
desde WA Web (Caminos 3 o 4).

---

## Archivos clave

| Archivo | Rol |
|---------|-----|
| `backend/automation/sync.py` | `delta_sync` + `StopCondition` — entry point unificado de scrape→.md |
| `backend/automation/whatsapp.py` | `scrape_full_history_v2`, `_poll_sidebar_for_delta`, `_run_delta_sync` |
| `backend/api/summarizer.py` | `_parse_messages`, `get_messages`, `sync_contact`, `full_resync_contact` |
| `backend/api/flows.py` | `_do_import`, `import_wa_history` |
| `backend/graphs/nodes/summarize.py` | `accumulate`, `_dedup_hash`, `_newest_message_ts` |
| `frontend/src/components/SummaryView.jsx` | UI de mensajes (burbujas, audio, imagen) |
| `frontend/src/components/BotCard.jsx` | `BrowserPanel` (siempre visible), `ConnectionRow` |

---

## Tests existentes

```bash
cd /Users/josetabuyo/Development/pulpo/_

# Unitarios — no requieren server
backend/.venv/bin/python -m pytest backend/tests/test_delta_sync.py -v       # 35 tests
backend/.venv/bin/python -m pytest backend/tests/test_whatsapp_sync.py -v    # 8 tests
backend/.venv/bin/python -m pytest backend/tests/test_auth.py backend/tests/test_logs.py backend/tests/test_sim.py -v  # 31 tests

# Todos los que pasan (requieren server en :8000)
backend/.venv/bin/python -m pytest backend/tests/ -v --tb=short
# → 66 passed, ~43 failed (test_contacts, test_bot, test_flows — problemas pre-existentes de configuración)
```

**Sin tests todavía:**
- Timestamp precision / ordering de mensajes
- Transcripción de audios en batch import
- `BrowserPanel` (UI)

---

## Datos de referencia

| Dato | Valor |
|------|-------|
| Flow ID garantido | `55f90118-a6f5-4c04-b775-b503a6748bfe` |
| Contacto de prueba | Andrés Buxareo |
| Número compartido | `5491155612767` |
| chat.md del contacto | `data/summaries/garantido/andres-buxareo/chat.md` |
| owner_name del número | `Jozbuyo` (en connections.json, gitignoreado) |
