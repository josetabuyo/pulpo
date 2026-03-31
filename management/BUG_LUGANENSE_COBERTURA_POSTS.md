# Bug: Luganense responde "buscá en Facebook" en lugar de buscar él mismo

**Fecha:** 2026-03-30
**Severidad:** Alta — afecta la propuesta de valor del bot
**Estado:** En progreso — BUG 1 y BUG 3 resueltos, BUG 2 pendiente

---

## Bugs y mejoras identificados (2026-03-31)

| ID | Descripción | Estado |
|----|-------------|--------|
| BUG 1 | Búsqueda headless no extrae contenido del feed | ✅ Resuelto |
| BUG 2 | No expande queries — bot busca solo la frase exacta | ⏳ Pendiente |
| BUG 3 | Mensajes outbound no se persisten en DB | ✅ Resuelto (commit 7f25786) |
| MEJORA 1 | Logs con primeras líneas de cada post + filtro por palabra clave en dashboard | ⏳ Pendiente |
| MEJORA 2 | Enviar imagen cuando el caso lo requiere (mascotas, noticias visuales) | ⏳ Pendiente |
| MEJORA 3 | Más tools de scraping (Información, Comunidad, Menciones) | ⏳ Pendiente |

---

## Detalle BUG 1 — Búsqueda headless no extrae contenido (RESUELTO)

**Causa raíz identificada (2026-03-31):** `_search_and_scrape` navegaba a la URL de búsqueda pero luego llamaba a `_scrape_posts`, que intenta recolectar links `/posts/pfbid` del DOM. Las páginas de búsqueda de Facebook no exponen esos links en el DOM — solo exponen links `/photo/?fbid=...`. Resultado: 0 URLs → 0 posts → respuesta vacía.

**Fix aplicado:** nueva función `_scrape_search_feed(page)` que:
1. Hace clic en todos los botones "Ver más" para expandir posts truncados
2. Lee el texto directamente del `[role='feed']` de la página de búsqueda
3. Retorna el contenido limpio (sin ruido UI) como contexto para el LLM

**Verificado en MCP browser:** la búsqueda `?q=milanesas` en el perfil numérico de Luganense devuelve el post de Sabor Peruano con el menú completo incluyendo "Milanesa", dirección, horario y teléfono.

---

## Detalle BUG 2 — Sin query expansion (PENDIENTE)

El grafo llama `fetch_facebook.fetch("luganense", state["message"])` con la frase exacta del usuario. Si el usuario pregunta "¿dónde como milanesas?" y el post dice "Milanesa", puede funcionar. Pero para queries ambiguas o con distancia semántica, sería mejor generar 2-3 términos de búsqueda alternativos con el LLM.

**Solución propuesta:** agregar nodo `expand_query` antes de `handle_noticias` que genere términos alternativos y llame `fetch` con cada uno, consolidando el contexto.

---

## Síntoma

Usuario pregunta: *"¿Dónde puedo comer milanesas?"*

Bot responde algo como:
> "No encontré información específica. Te sugiero buscar en la página de Facebook de Luganense."

El bot le dice al usuario que haga lo que el bot debería hacer. Es la falla más visible para el usuario.

---

## Evidencia en logs

```
2026-03-30 23:25:16 INFO  [luganense] scope_router → 'noticias'
2026-03-30 23:25:48 INFO  [luganense] handle_noticias: respuesta generada (720 chars)
```

Pipeline nuevo funciona (sin ReAct error). El problema es el contenido scrapeado, no el pipeline.

---

## Causa raíz

### El post de la pollería es un Reel

La publicación de Luganense que menciona "✔ Milanesa" está publicada como Reel (`/reel/2370482426798630`).

En scraping headless con Playwright:
- Páginas de Reel → 0 artículos renderizados
- El contenido (menú completo) está dentro del overlay del video
- El botón "Ver más" del overlay no existe en headless
- Resultado: el reel scrapeado = solo imagen, sin texto del menú

### Los 5 seeds no cubren ese post

```python
_SEED_URLS = {
    "luganense": [
        # Destacados (herrería, YouTube cultural) — no hay comida
        "pfbid0UYq8...",  # GM Herrería
        "pfbid0y3qN...",  # YouTube cultural
        # Posts recientes — tampoco incluyen menú de pollería
        "pfbid0ztrsk...", # Heladería Lordie
        "pfbid02ybis...", # Perro/mascota
        "pfbid02eMA9...", # Bridge/camioneros
    ]
}
```

Ninguno de los 5 seeds contiene un menú de comida con milanesas.

### El feed headless tampoco lo carga

El feed de Facebook en headless con la cuenta jtabuyo@hotmail.com renderiza ~1 artículo adicional. Los reels no aparecen en el feed headless de todas formas.

---

## Bug secundario detectado

**Las respuestas del bot no se guardan en la DB.**

La tabla `messages` solo almacena mensajes inbound (del usuario). Las respuestas outbound del bot (`outbound=1`) no se persisten. Esto impide:
- Ver la respuesta exacta que dio el bot en el admin
- Auditar la calidad de respuestas
- Depurar bugs de contenido sin acceso a Telegram directamente

---

## Opciones de resolución

### Opción A — Agregar seed pfbid del menú de la pollería (rápido, manual)
Si existe una versión no-reel del mismo post (foto + texto), agregar su URL a `_SEED_URLS`.

**Cómo encontrarlo:** visitar `facebook.com/luganense` con MCP browser, buscar posts recientes de la pollería que sean fotos (no reels), copiar el pfbid.

**Limitación:** requiere actualización manual cada vez que cambia el menú.

### Opción B — Actualizar seeds semanalmente (semi-manual)
Proceso: cada semana, visitar Luganense con MCP browser, extraer URLs de los 5 posts más recientes, actualizar `_SEED_URLS`. Puede automatizarse con un script + cron.

### Opción C — Cuenta FB dedicada (mejor cobertura)
Crear una cuenta FB que siga activamente a Luganense. Con una cuenta más activa, el feed headless renderiza más posts (incluyendo potencialmente los reels con sus thumbnails de texto).

### Opción D — Graph API oficial
Si Luganense otorga un Page Access Token, reemplazar el scraping headless por Graph API. Acceso completo a todos los posts sin restricciones de headless.

**Esta es la solución definitiva a largo plazo.**

---

## Resolución del bug secundario (outbound no guardado)

Buscar en el código dónde se envía la respuesta por Telegram y agregar persistencia:

```python
# En el handler de Telegram, después de enviar la respuesta:
await save_message(
    bot_id=empresa_id,
    phone=str(chat_id),
    name="Bot",
    body=reply,
    outbound=True,
)
```

Esto permite ver en el admin la conversación completa (pregunta + respuesta).

---

## Próximos pasos sugeridos

1. **Corto plazo:** buscar con MCP browser un post pfbid de la pollería y agregarlo a seeds
2. **Mediano plazo:** script de actualización semanal de seeds
3. **Largo plazo:** Graph API oficial con Luganense
4. **Separado:** fix de persistencia de mensajes outbound
