# NEXT_SESSION — Luganense MEJORA 1: logs ricos por post scrapeado

## Contexto
Worktree: `bug-luganense` | Backend: `:8002` | `ENABLE_BOTS=false`
Arrancar: `./start.sh` desde la raíz de este worktree.

El bot Luganense ya funciona correctamente en producción (búsqueda headless + query expansion).
Esta sesión implementa la MEJORA 1 del doc `management/BUG_LUGANENSE.md`.

---

## Regla de esta sesión

Al terminar: **commit en bug-luganense → merge a master → push → restart backend de producción**.
Misma secuencia que la sesión anterior.

---

## Tests antes de empezar

Los tests apuntan a **master** (`:8000`). Asegurarse de que esté corriendo:
```bash
curl -s http://localhost:8000/health   # debe responder {"status":"ok","bots":2}
```

Correr desde la raíz del worktree (el conftest usa el puerto del .env del worktree — verificar que apunte a :8000, o correr contra el backend de master):
```bash
cd /Users/josetabuyo/Development/pulpo/_/backend
pytest tests/test_auth.py tests/test_logs.py tests/test_sim.py tests/test_summarizer.py -v
```

Baseline esperado: **41 passed, 2 failed pre-existing** (no son nuestros):
- `test_sim_send_appears_in_log` — timing del log file, intermitente
- `test_sim_receive_con_audio_path` — sqlalchemy no instalado en Python sistema

Si hay más fallos, investigar antes de tocar código.

---

## MEJORA 1 — Logs con primeras líneas de cada post scrapeado

### Problema actual
Los logs de fetch_facebook muestran solo conteos:
```
[fetch_facebook] 6 posts extraídos para 'luganense'
```
No se puede saber qué posts llegaron al LLM ni si eran relevantes para la pregunta.

### Lo que queremos ver
```
[fetch_facebook] queries: ['Pola y Hubac', 'Pola', 'Hubac']
[fetch_facebook] post 1 (Pola y Hubac): "Sergio encontró un perro en Oliden y Castañares..."
[fetch_facebook] post 2 (Pola): "Se busca a quien perdió su perro en la zona de Pola..."
[fetch_facebook] post 3 (static): "🍗 ¡ATENCIÓN VILLA LUGANO! Llegó una nueva pollería..."
```

### Implementación

**Archivo:** `backend/nodes/fetch_facebook.py`

**1. Loguear cada post scrapeado** en `_scrape_search_feed` y en `_scrape_posts`:
```python
for i, post in enumerate(posts):
    logger.info("[fetch_facebook] post %d: %s", i + 1, post[:80].replace('\n', ' '))
```

**2. Loguear las queries en `handle_noticias`** (`backend/graphs/luganense.py`):
```python
logger.info("[luganense] queries: %s", queries)
```
Ya existe el log `"queries generadas"` en `_expand_queries` — verificar que sea suficiente
o agregar uno en `handle_noticias` que muestre cuántas queries y cuántos chars de contexto resultaron.

**3. Loguear el contexto final** (cuántos chars llegaron al LLM):
```python
logger.info("[luganense] contexto FB: %d chars de %d queries", len(fb_context), len(queries))
```

### Tests a escribir

Archivo: `backend/tests/test_fetch_facebook_logs.py`

```python
"""Tests que verifican que fetch_facebook logea correctamente los posts."""

def test_static_posts_aparecen_en_logs(caplog):
    """Los static posts deben aparecer en los logs aunque el browser falle."""
    # Mockear _load para que devuelva vacío (simula fallo del browser)
    # Llamar fetch("luganense", "milanesas")
    # Verificar que el log menciona "[fetch_facebook] post" con texto del static post

def test_log_incluye_primeras_lineas_del_post(caplog):
    """El log de cada post debe incluir las primeras ~80 chars del texto."""
    # Mockear _load para devolver texto conocido
    # Verificar formato del log
```

> Nota: estos tests son unitarios (no necesitan browser). Mockear `_load` con `unittest.mock.patch`.

---

## Checklist de cierre

- [ ] Tests existentes pasan (mismos 41 que antes)
- [ ] Tests nuevos de logs escritos y verdes
- [ ] `pytest tests/ -v` sin nuevos fallos
- [ ] `git add` + `git commit` en `bug-luganense`
- [ ] `cd /Users/josetabuyo/Development/pulpo/_ && git merge bug-luganense`
- [ ] `git push origin master`
- [ ] `./restart-backend.sh`
- [ ] `curl -s http://localhost:8000/health` → `{"status":"ok","bots":2}`
