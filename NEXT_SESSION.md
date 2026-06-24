# NEXT SESSION — Pipeline FB completado

## Estado (sesión 2026-06-24)

Los tres pasos del pipeline FB están completos. No hay deuda pendiente en este tema.

---

### ✅ Paso 1 — Links en respuestas del LLM

**Qué se hizo:**
- Bug corregido: `_NOTICIAS_SYSTEM` no tenía cierre `"""` → `_AUSPICIANTE_SYSTEM` quedaba embebido
  como texto y nunca era una variable Python (la rama `auspiciante` tiraba `NameError`).
- `responder_noticias` ahora arma el contexto con `Link: <url>` antes del texto de cada post.
- Prompt del LLM actualizado: le indica que cite el link al final de la oración relevante.
- Error path de `_scrape_post_page` corregido: ahora siempre retorna `{"url": url, ...}`.

**Archivos:**
- `backend/graphs/luganense.py` — líneas 68, 217, prompt `_NOTICIAS_SYSTEM`
- `backend/nodes/fetch_facebook.py` — línea 293

---

### ✅ Paso 2 — Límite de contexto

**Resultado:** sin cambios necesarios.
El modelo es `llama-3.3-70b-versatile` (Groq) con 128k tokens de contexto.
30 posts × ~600 tokens = ~18k tokens → caben holgado.

---

### ✅ Paso 3 — Cache como read-through (sin LLM)

**Qué se hizo:**
- `buscar_posts_fb` ahora chequea `fb_cache.get_by_query` antes de scrapear FB.
- Si la query tiene posts en cache con menos de 24h de antigüedad → los reutiliza, no toca FB.
- Solo scrapea las queries sin cache hit.
- `get_by_query` acepta `max_age` (segundos); 0 = sin límite.
- El dedup semántico es implícito: `expandir_consulta` normaliza las queries
  ("perdí mi perro" → "perro perdido"), así queries equivalentes reutilizan la misma entrada de cache.

**Archivos:**
- `backend/nodes/fb_cache.py` — `get_by_query(max_age=)`
- `backend/graphs/luganense.py` — `buscar_posts_fb` (lógica cache-first)

---

## Tests

```bash
backend/.venv/bin/pytest backend/tests/test_fb_cache.py -v   # 10/10
```

## Cómo verificar en vivo

```bash
# Ver posts cacheados con sus URLs
qdb "SELECT url, substr(text,1,60) FROM fb_posts WHERE page_id='luganense' LIMIT 10"

# Ver queries guardadas
qdb "SELECT query, found_at FROM fb_post_queries ORDER BY found_at DESC LIMIT 10"

# Test de scraping real (abre browser visible)
backend/.venv/bin/python scripts/test_fb_debug.py --visible "perro perdido"
```

En los logs del backend, el cache hit se ve como:
```
[luganense] cache hit 'perro perdido': 12 posts (sin scrapear FB)
```
