# BUG: Links de fuentes en respuestas Luganense

## Estado
**Temporalmente desactivado** — solo se devuelve el primer link mientras no se resuelva.

## Descripción del bug

Cuando el flow de Luganense responde sobre noticias del barrio, el nodo `FetchNode`
scrapea Facebook con hasta 3 queries en paralelo y guarda hasta 3 URLs en `state.vars["source_urls"]`.
Luego `telegram_bot.py` las appendea todas al reply como "📎 Ver publicación 1/2/3".

El problema es que **solo el primer link tiene sentido**: es el post más relevante que encontró
la búsqueda principal. Los siguientes links corresponden a búsquedas expandidas secundarias
(generadas por `expandir_consulta`) que suelen ser posts relacionados lateralmente, con poca
relevancia para la pregunta original del vecino.

Resultado: el vecino recibe 3 links, 2 de los cuales no tienen relación directa con lo que preguntó.

## Workaround aplicado

`fetch.py:82` — cambiado `source_urls[:3]` → `source_urls[:1]`

## Solución futura

Para devolver múltiples links con sentido, necesitamos:

1. **Rankear los posts** por relevancia a la query original (no a las queries expandidas)
2. **Filtrar** antes de construir `source_urls`: solo incluir posts cuyo texto el LLM realmente citó en el reply
3. O bien **no generar links** para las búsquedas secundarias — solo para la búsqueda principal

Archivos involucrados:
- `backend/graphs/nodes/fetch.py` — línea 82 (construcción de `source_urls`)
- `backend/bots/telegram_bot.py` — líneas 90-95 (append al reply)
- `backend/graphs/luganense.py` — `buscar_posts_fb` / `expandir_consulta`
