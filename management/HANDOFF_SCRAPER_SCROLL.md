# Handoff: Scraper WA — Scroll, Zoom y Orden de Mensajes

**Fecha:** 2026-05-16  
**Sesión:** Muy extensa, se cortó por tamaño. Continuar aquí.

---

## Estado actual del sistema

- Backend corriendo en `_` (master), puerto 8000, bots OK (`curl localhost:8000/health`)
- CSS zoom global `0.5` en `document.documentElement` via `context.add_init_script` — aplicado siempre (thumbnail y scrape)
- Viewport 2400px durante scrape (restaurado a original en finally)
- Compensación de zoom en scroll: `_step_px × _page_zoom` para que el wheel event mueva la misma distancia que antes

## Problema activo principal: orden y fechas incorrectas

### Los dos primeros mensajes del chat (garantido/andres-buxareo) tienen fecha MAL asignada

Los mensajes:
1. Audio: "Hola José, ¿cómo estás? Buenas tardes... Te habla Andrés, el hermano de Mayra"
2. Audio: "Ando justo manejando en ruta..."

**Fecha real:** 2026-05-04 ~14:22-14:23 (los primeros mensajes del chat, antes del "Gracias" a las 14:23)  
**Fecha asignada:** 2026-05-13 14:22-14:23 → aparecen en posición 97/98 de 105, al final

**Por qué:** Estos son audios sin `data-pre-plain-text`. La función `_nearestDateBefore()` busca el separador de fecha más cercano **antes** del mensaje en el DOM. Cuando WA los carga via CARGA_WA (el primer CARGA_WA al llegar al tope), el separador "Lunes, 4 de mayo de 2026" NO está en el DOM (está virtualizado porque está por encima del viewport). Entonces `_nearestDateBefore()` encuentra el separador "Martes, 13 de mayo" y le asigna esa fecha.

**Archivo:** `backend/automation/whatsapp.py` — función `_nearestDateBefore` en `_DATE_HELPERS_JS` (buscar `_nearestDateBefore` en el archivo, está en un string JS grande)

### Propuesta de fix para las fechas

**Fix 1 (bidireccional):** cuando `_nearestDateBefore` no encuentra separador hacia atrás, buscar también hacia adelante. El primer mensaje del chat puede tener el separador de fecha DESPUÉS de él (WA lo carga como header del día siguiente).

**Fix 2 (consistencia):** en el post-process Python, detectar mensajes cuya fecha asignada es POSTERIOR a la del mensaje siguiente que tiene fecha conocida (con `data-pre-plain-text`). En ese caso, la fecha es incorrecta — usar la fecha del mensaje anterior con fecha conocida.

**Fix 3 (enfoque del usuario — el correcto):** El usuario dice que lo indispensable es el ORDEN, no la fecha exacta. La posición en pantalla define el orden de la conversación. Hay que sortear el chat.md por posición DOM en lugar de timestamp.

### Propuesta de fix para el orden

Actualmente `chat.md` se ordena por timestamp en el merge. En vez de eso, usar la posición absoluta en el DOM:

En el scan JS, ya tenemos `top` (rect.top del elemento). También tenemos `_scroll_after` (scrollTop al final del round). La posición absoluta = `scrollTop_at_capture + top`. Esto define el orden relativo dentro de cada ronda.

Para un sort global estable: capturar `dom_idx` (índice del elemento en `querySelectorAll('.message-in, .message-out')`) durante el scan. WA siempre inserta mensajes viejos al PRINCIPIO del DOM (índice 0,1,2...) y los nuevos al FINAL. El índice DOM en el momento de captura refleja el orden de la conversación.

El sort final debería usar: `(fecha si confiable, si no: dom_idx_capture)` como clave.

**Archivo clave para el merge:** buscar dónde se escribe `chat.md` y cómo se ordenan los mensajes. Probablemente en `backend/api/summarizer.py`.

---

## Estado del scroll (sesión actual)

### Lo que funcionó antes (16:12, 118 mensajes, 5 CARGA_WA)
- `document.body.style.zoom = 0.5` aplicado solo durante scrape
- `viewport = 2400px` 
- `scroll_step = 300` (default)
- Sin compensación de zoom (el body zoom no afectaba scrollTop)

### Lo que tenemos ahora
- `document.documentElement.style.zoom = 0.5` global (siempre)
- `viewport = 2400px` durante scrape
- Compensación: `step_px × _page_zoom (0.5)` en near-top
- Compensación + `viewport_scale (3x)` en modo agresivo (lejos del tope)
- Force `scrollTop = 0` + 8s wait + jiggle (scroll +200px → scroll 0 → 3s wait) al llegar al tope absoluto
- Go-to-bottom robusto con verificación al abrir chat

### Problema abierto con la cobertura
Máximo conseguido: 120 mensajes. El usuario contó 143 en WA. Los 23 restantes son los más antiguos (antes del 5 de mayo).

Los runs recientes dan 105 porque `viewport_scale = 3` en near-top hizo los pasos demasiado grandes y se barrian mensajes. Fix aplicado en esta sesión: near-top ya NO usa viewport_scale (solo usa `_page_zoom`).

**Necesita restart + prueba** al continuar la sesión.

### CARGA_WA: solo 1 evento vs los 5 que necesitamos
Con `documentElement.style.zoom=0.5`, WA parece cargar solo 1 batch via CARGA_WA aunque el usuario tiene 143 mensajes. Con el enfoque anterior (`body.style.zoom=0.5`) se obtenían 5 batches.

**Teoría:** la diferencia entre `body.style.zoom` y `documentElement.style.zoom` cambia cómo WA's IntersectionObserver detecta el sentinel de carga. Con documentElement zoom, los coordinates del IntersectionObserver también están escalados, lo que puede afectar cuándo WA considera que el sentinel es visible.

**Alternativa a explorar:** volver a `body.style.zoom=0.5` DURANTE el scrape (no como zoom global — ese ya lo tenemos en documentElement). Aplicar body zoom al inicio de `scrape_full_history_v2` y quitarlo en finally, igual que antes. Esto mantendría el zoom global para el thumbnail y usaría el enfoque que YA SABEMOS que dispara 5 CARGA_WA.

---

## Cambios en el código esta sesión (resumen para git)

Todos en `backend/automation/whatsapp.py`:

1. **`get_or_create_page()`**: zoom global 0.5 en `documentElement` via `add_init_script` + `evaluate` inmediato en página actual
2. **`scrape_full_history_v2()`**:
   - `_orig_viewport` inicializado ANTES del try block
   - Viewport 2400px al inicio del scrape (restaurado en finally)
   - `_page_zoom` leído de la página para compensación
   - `_viewport_scale = viewport_h / 800` calculado
   - Near-top: `step_px = max(20, int(scroll_step//4 * _page_zoom))` (sin viewport_scale)
   - Aggressive: `step_px = max(40, int(scroll_step//2 * _page_zoom * viewport_scale))`
   - At-top: force `scrollTop=0` + 8s wait + jiggle + 3s wait
   - Go-to-bottom robusto con verificación al inicio
   - Stale threshold `_near_top` escalado por zoom: `500 * _page_zoom`

---

## Para retomar: pasos inmediatos

1. `./restart-backend.sh` (hay un cambio pendiente: near-top sin viewport_scale)
2. Correr full-sync en garantido/andres-buxareo y ver si mejora de 105
3. Revisar si hay más CARGA_WA que antes
4. Si sigue en ~120 y no llega a 143: explorar volver a `body.style.zoom` durante scrape
5. Fix de fechas: `_nearestDateBefore()` bidireccional O sort por DOM position
6. Fix de orden: usar dom_idx o y_absolute como sort key en lugar de timestamp

## Archivo de tests
`backend/tests/test_browser_zoom.py` — 4 tests, todos pasan (`pytest tests/test_browser_zoom.py -v`)
