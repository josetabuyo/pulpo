# Handoff: Extracción de URLs — iteración 3

**Fecha:** 2026-06-24  
**Contexto:** nodo fetch_facebook del graph Luganense  
**Worktree:** `_` (master/producción)

---

## Problema

Al buscar "perro perdido" en el feed de luganense, Facebook muestra muchos posts.
Sin embargo solo capturamos 3 URLs. Eso es porque `_extract_article_urls` busca
links `<a href>` con patrones `/posts/`, `/permalink.php`, `/share/p/` dentro de
cada `[role="article"]` — y la mayoría de los articles no tienen ningún link que
matchee esos patrones.

**Las 3 URLs que tenemos son todas reshares del mismo post** (mismo texto, distinto
`share/p/` ID). Necesitamos una URL diferente por cada post distinto.

---

## Por qué falla el approach actual

Facebook en sus resultados de búsqueda (`/profile/{id}/search?q=...`) no siempre
pone el link de permalink en el timestamp como un `<a href>` directo. Puede:

1. Usar `href` con otros patrones no contemplados (`/story.php?story_fbid=...`)
2. Renderizar el timestamp como un elemento con `onclick` en vez de `<a href>`
3. Tener el permalink como atributo `aria-label` en vez de `href`
4. El `<a>` existe pero el `href` es relativo o usa encoding raro de Facebook

El código actual tiene `max_posts=5`, con lógica `break` al primer match por article.
Si los primeros 5 articles no tienen links con los patrones, devuelve vacío.

---

## Qué hacer: debug primero

### Paso 1 — Loggear qué hay en cada article

Agregar logging detallado en `_extract_article_urls` **cuando FB_DEBUG=1**:
para cada article, imprimir TODOS los `href` que tiene (no solo los que matchean).
Esto dice exactamente qué patrones usa Facebook en el DOM real.

```python
if os.getenv("FB_DEBUG"):
    all_hrefs = []
    for link in links:
        h = await link.get_attribute("href") or ""
        if h and h not in ("#", ""):
            all_hrefs.append(h[:100])
    logger.info("[fetch_facebook] article %d hrefs: %s", i, all_hrefs[:10])
```

### Paso 2 — Correr el debug

```bash
FB_DEBUG=1 python scripts/test_fb_debug.py "perro perdido"
```

Ver en los logs:
- ¿Cuántos articles se encuentran?
- ¿Qué hrefs tienen los que NO generan URL?
- ¿Hay algún patrón alternativo consistente?

### Paso 3 — Inspeccionar el DOM vivo

Con el browser abierto (FB_DEBUG pausa 60s), usar `playwright-cli` en otra sesión
para inspeccionar los elements y ver qué tiene el timestamp de cada post.

---

## Fix propuesto (implementar después del debug)

### Estrategia: JS full-feed scan

En vez de recorrer article por article con Playwright, hacer un único `page.evaluate()`
que escanea todo el DOM en busca de links que matcheen cualquier patrón de permalink.
Es más rápido, más robusto, y no depende de que el selector `[role="article"]` esté bien.

```python
_PERMALINK_PATTERNS_JS = ["/posts/", "/permalink.php", "/share/p/", "/story.php"]

async def _extract_feed_urls(page, max_posts: int = 10) -> list[str]:
    """
    Extrae URLs de posts usando JS para escanear todo el DOM del feed.
    Más robusto: no depende de estructura de [role="article"].
    """
    patterns = _PERMALINK_PATTERNS_JS
    try:
        urls = await page.evaluate("""(patterns) => {
            const seen = new Set();
            const result = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;  // URL absoluta, resuelta por el browser
                if (!href || href === window.location.href) continue;
                if (patterns.some(p => href.includes(p))) {
                    const base = href.split('?')[0];
                    if (!seen.has(base)) {
                        seen.add(base);
                        result.push(base);
                    }
                }
            }
            return result;
        }""", patterns)
        logger.info("[fetch_facebook] feed scan: %d URLs encontradas", len(urls))
        return urls[:max_posts]
    except Exception as e:
        logger.warning("[fetch_facebook] Error en feed scan: %s", e)
        return []
```

Ventajas del approach JS:
- `a.href` resuelve la URL absoluta (maneja relativos y encoding de Facebook)
- Un solo call al browser en vez de N calls por article
- Fácil de ampliar con más patrones sin tocar selectores
- El `split('?')[0]` elimina tracking params

### Patrones a verificar en el debug

Además de los actuales, agregar en `_PERMALINK_PATTERNS_JS`:
- `/story.php` — formato viejo de Facebook
- `story_fbid` — aparece en some permalink query strings (usar split antes del `?` para filtrar)
- `/reel/` — si hay reels mezclados en el feed

### `_search_and_scrape` — no cambia la estructura

Solo cambia la llamada: `_extract_article_urls(page)` → `_extract_feed_urls(page)`.
El resto del flujo (scrape individual de cada URL vía `_scrape_post_page`) sigue igual.

### Criterio de done

Correr `python scripts/test_fb_debug.py "perro perdido" "accidente" "perro perdido"`:
- Al menos 5 URLs distintas para "perro perdido" (hay muchos posts)
- Cada URL apunta a un post diferente (textos distintos)
- Ninguna URL es `facebook.com/luganense` ni `story.php` sin fbid

---

## Archivos a tocar

| Archivo | Qué hacer |
|---------|-----------|
| `backend/nodes/fetch_facebook.py` | Agregar log de hrefs en debug; reemplazar `_extract_article_urls` por `_extract_feed_urls` con JS |

## No tocar

Todo lo demás — `fb_cache.py`, `luganense.py`, tests existentes.

---

## Notas de arquitectura

- `_scrape_post_page(ctx, url)` ya existe y funciona: navega a cada URL y extrae texto.
  El bottleneck de performance es que hacemos N requests individuales (uno por post).
  Aceptable por ahora — 5-10 posts son 5-10 requests en secuencia.
- Si el debug muestra que los resultados de búsqueda no tienen links clickeables en el DOM
  (todo es JS-driven), el fallback sería capturar las URLs del tráfico de red con
  `page.on("response")` durante el scroll. Eso es más complejo — solo si el JS scan falla.
