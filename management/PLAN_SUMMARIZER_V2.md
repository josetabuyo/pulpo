# Plan: Summarizer V2 — Carpeta por contacto, arquitectura mensaje-primero

## Estado al iniciar este plan
- `scrape_full_history_v2` escrito (arquitectura mensaje-primero, sin IDB)
- Endpoints `full-resync` y `sync` en `api/summarizer.py`
- UI tiene botón `⟳ Full` y `↻` delta sync
- Estructura de archivos actual: `.md` suelto + carpeta de adjuntos separada (a migrar)

---

## Estructura de archivos objetivo

```
data/summaries/{empresa_id}/
  {contact-slug}/          ← una carpeta por contacto
    chat.md                ← historial completo en texto
    fabian-miranda.jpg     ← imágenes descargadas
    documento.pdf          ← docs descargados
    ...
```

**Slug del contacto:** kebab-case, lowercase, sin acentos, sin caracteres especiales.
Siempre se usa el **nombre del contacto**. El número de teléfono es un bug.
- `"Fabian Miranda"` → `fabian-miranda`
- `"Desarrollo SIGIRH  2025"` → `desarrollo-sigirh-2025`
- Sin nombre (raro): número como fallback temporal → renombrar cuando llegue el nombre
- Función: `slugify(name: str) -> str` en `graphs/nodes/summarize.py`

La UI lee **directamente de la carpeta**, no de la DB.

---

## Proceso delta sync — orden causal (inmutable)

```
1. Backup     → copiar chat.md a chat.bak.md dentro de la misma carpeta
2. Trim       → borrar del chat.md y DB todo con timestamp >= fecha_input
3. Abrir chat → WA Web, posicionarse en el mensaje más nuevo (fondo)
4. Loop       → mensaje por mensaje hacia arriba:
     a. Procesar atómicamente:
          - Texto    → guardar
          - Audio    → click play → esperar blob (retry 3x, 15s c/u) → transcribir
          - Doc      → descargar a la carpeta del contacto
          - Imagen   → descargar blob a la carpeta del contacto
     b. Guardar en DB + chat.md
     c. Si timestamp < fecha_input → STOP
5. Fin
```

El paso 4a (procesador atómico) es el que crece con más casos.
Los pasos 1-5 no cambian.

---

## Cambios por capa

### Backend — `graphs/nodes/summarize.py`
- [ ] `slugify(name: str) -> str`
- [ ] `_path(empresa_id, contact_slug)` → apunta a `{slug}/chat.md`
- [ ] `get_attachments_dir` → devuelve `{slug}/` (misma carpeta que el md)
- [ ] `_newest_message_ts` → lee de `chat.md`
- [ ] `trim_contact_to_date(empresa_id, slug, cutoff_dt)`:
      - Backup de `chat.md` → `chat.bak.md`
      - Reescribe `chat.md` conservando solo entradas con `ts < cutoff_dt`
      - DELETE en DB: `timestamp >= cutoff_dt` para ese contacto
- [ ] Migración de datos existentes: `.md` sueltos → `{slug}/chat.md`

### Backend — `automation/whatsapp.py`
- [ ] `scrape_full_history_v2` ya usa arquitectura mensaje-primero ✅
- [ ] Conectar `stop_before_ts` al trim (parar cuando `ts < cutoff_dt`)
- [ ] Retry en captura de blob de audio (3 intentos antes de marcar sin blob)

### Backend — `api/summarizer.py`
- [ ] `POST /summarizer/{empresa_id}/{contact_slug}/full-resync?from_date=YYYY-MM-DD`
      → trim → delta sync v2
- [ ] Endpoints existentes adaptar a slug en vez de contact_phone
- [ ] `GET /summarizer/{empresa_id}` → lista carpetas (slugs + nombre real)

### Backend — `api/whatsapp.py`
- [ ] Delta sync periódico: integrar en el polling loop del trigger
- [ ] Intervalo configurable (default 4 min) desde config del nodo trigger

### Frontend — `SummaryView.jsx`
- [ ] Leer mensajes desde la carpeta (hoy lee de un endpoint que parsea el md) ✅ (no cambia)
- [ ] Botón `⟳ Full` → reemplazar por panel de propiedades del trigger node

### Frontend — `FlowEditor` / nodo trigger
- [ ] Panel de propiedades del nodo `whatsapp_trigger`:
      - Campo: intervalo de polling (ya existe)
      - Campo: countdown (ya existe)
      - Campo: fecha límite de re-sync (date picker)
      - Botón: `⟳ Re-sync desde esta fecha` → llama a `full-resync?from_date=...`

---

## Orden de ejecución

1. `slugify` + migración de carpetas existentes (no rompe nada, es additive)
2. `trim_contact_to_date` + endpoint `full-resync` con fecha
3. Conectar delta sync al polling del trigger node (intervalo 4 min)
4. UI: date picker + botón en panel del trigger node
5. Tests

---

## Notas

- **Telegram:** usa long-polling de python-telegram-bot, mensajes llegan en tiempo real.
  No aplica el scraping periódico. El summarizer de Telegram acumula directamente
  en el handler de mensajes. Resolver por separado.
- **Archivos/imágenes:** nunca se borran en el trim. Solo se recorta el md y la DB.
- **IDB:** eliminado definitivamente. Solo blob directo o `[audio — sin blob]`.
