# BUG_LUGANENSE — Bugs y mejoras del bot Luganense

**Última actualización:** 2026-03-31

---

## Estado resuelto (sesión 2026-03-31)

| ID | Descripción | Estado |
|----|-------------|--------|
| BUG 1 | Búsqueda headless no extraía contenido del feed | ✅ Resuelto |
| BUG 2 | Bot buscaba solo la frase exacta del usuario | ✅ Resuelto |
| BUG 3 | Respuestas outbound no se guardaban en DB | ✅ Resuelto |

### Cómo se resolvió BUG 1
El headless sí veía los posts pero los recibía truncados con "… Ver más". El código buscaba `<button>` pero en las páginas de búsqueda de FB el "Ver más" es un `div[role='button']`. Con el selector ampliado (`[role='button'], button, a`) el texto se expande correctamente.

También se agregó `FB_DEBUG=1` como variable de entorno que guarda screenshots en `data/debug/` para poder diagnosticar visualmente qué ve el headless.

### Cómo se resolvió BUG 2
Se implementó query expansion con múltiples búsquedas paralelas:
- Groq genera 1-3 queries específicas a partir del mensaje del usuario
- `asyncio.gather` las corre en paralelo (sin overhead de latencia)
- Los resultados se combinan y deduiplican antes de pasarlos al LLM

Regla especial para intersecciones: `"Pola y Hubac"` → `["Pola y Hubac", "Pola", "Hubac"]`

Validado en producción: "encontré un perro en Pola y Hubac, quiero devolverlo" → bot respondió con el nombre y teléfono del dueño del perro (Sergio) tomado de un post real de Facebook.

### Cómo se resolvió BUG 3
En `telegram_bot.py`, después de `await msg.reply_text(reply)`, se agregó `await log_message(..., outbound=True)`.

---

## Próxima etapa — mejoras con modelo pago

La calidad del query expansion y las respuestas mejorará significativamente con un modelo de pago (GPT-4o, Claude, etc.). El modelo actual (llama-3.3-70b-versatile via Groq) funciona bien pero tiene limitaciones en razonamiento fino.

---

## Mejoras pendientes (baja prioridad)

| ID | Descripción |
|----|-------------|
| MEJORA 1 | Logs con primeras líneas de cada post en el dashboard |
| MEJORA 2 | Enviar imagen cuando el caso lo requiere (mascotas, noticias visuales) |
| MEJORA 3 | Más tools de scraping (Información, Comunidad, Menciones de FB) |
