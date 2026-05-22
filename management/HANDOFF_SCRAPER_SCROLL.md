# Handoff: Scraper WA — Fechas, Orden y Cobertura

**Fecha:** 2026-05-17  
**Chat de prueba:** `garantido/andres-buxareo`

---

## Estado del sistema

- Backend corriendo en `_` (master), puerto 8000, bots OK (`curl localhost:8000/health`)
- `body.style.zoom = 0.5` aplicado SOLO durante scrape (después del go-to-bottom), quitado en `finally`
- `documentElement.style.zoom` NO se usa (se removió — interfería con IntersectionObserver de WA)
- Viewport 2400px durante scrape (restaurado en `finally`)
- `_page_zoom = documentElement.zoom × body.zoom` (fix ya aplicado)

## Resultados actuales

- **118 mensajes** en `chat.md` (usuario dice 143 en WA)
- **CARGA_WA**: 2 eventos → 2 batches cargados
- **Fechas corregidas**: ids 1-3 ahora muestran `2026-05-04` correctamente (antes: `2026-05-13`)

---

## ✅ Tareas completadas (commit 3b91974)

### Tarea 1 — Fix `_nearestDateBefore()` bidireccional
**Archivo:** `backend/automation/whatsapp.py`  
**Estado:** APLICADO Y VERIFICADO

Los primeros 3 mensajes del chat (audios sin `data-pre-plain-text` cuyo separador de día está
virtualizado fuera del DOM cuando se carga el primer batch) ahora toman la fecha del separador
siguiente en lugar de quedarse vacíos y caer al fallback del 13-mayo.

### Tarea 3 — Fix permanencia de `name.txt`
**Archivo:** `backend/api/summarizer.py`  
**Estado:** APLICADO Y VERIFICADO

`full_resync_contact` ahora re-guarda `name.txt` con el nombre resuelto ANTES de llamar a
`clear_contact_full`. Esto garantiza que el nombre correcto ("Andrés Buxareo") persiste
tras el clear para futuros resyncs. Sin este fix, `accumulate` no recrea `name.txt` cuando
`slug == slugify(slug)`, y el próximo resync usa el slug como nombre de búsqueda en WA → 0 msgs.

**Nota importante:** si `garantido` no tiene contactos en la DB Y `name.txt` está ausente,
el nombre resuelto será el slug. En ese caso hacer manualmente antes de un resync:
```bash
printf 'Andrés Buxareo' > data/summaries/garantido/andres-buxareo/name.txt
```
Después del primer resync exitoso, `name.txt` se auto-mantiene.

---

## Tareas pendientes

### Tarea 2: Fix sort por posición DOM (evaluación post-fix-fechas)

Con las fechas corregidas, evaluar si el sort por timestamp sigue siendo problemático.

**Archivo:** `backend/automation/sync.py`  
**Línea:** ~95  
**Código actual:**
```python
messages.sort(key=lambda m: m.get("timestamp") or "")
```

**Estado:** PENDIENTE — esperar para ver si los 118 mensajes tienen orden correcto sin más fixes.

### Tarea 4: Investigar 25 mensajes faltantes

118 capturados vs 143 en WA. CARGA_WA se activa 2 veces solamente.

**Posibles causas:**
- El 3er batch (mensajes de antes del 5 de mayo) no dispara CARGA_WA en headless
- Los mensajes pueden no estar sincronizados a WA Web (solo en el dispositivo móvil)
- El viewport de 2400px + zoom 0.5 = 1200px efectivos de área visible → sentinel del 3er batch
  puede no entrar en el viewport

**Para investigar:** en los logs del scrape, buscar la secuencia de scrollTop justo antes del
jiggle final. Si scrollTop llega a 0 pero CARGA_WA no se activa la 3a vez, el problema es
el IntersectionObserver en headless.

---

## Cambios aplicados en sesiones anteriores (ya en master)

Todos en `backend/automation/whatsapp.py`:
1. `body.style.zoom = 0.5` solo durante scrape (post go-to-bottom) — quitado de documentElement
2. `_page_zoom = documentElement.zoom × body.zoom` (fix del cálculo incorrecto)
3. Near-top: `step_px = max(20, int(scroll_step//4 * _page_zoom))` (sin viewport_scale)
4. Aggressive: mismo step_px que near-top, 20 wheel_steps
5. At-top: force scrollTop=0 + 8s wait + jiggle + 3s wait
6. Go-to-bottom robusto con verificación al inicio

En `backend/api/summarizer.py`:
- Fix ImportError: `from db import get_contacts`
- Re-guardar `name.txt` después de `clear_contact_full`

En `backend/automation/whatsapp.py`:
- `_nearestDateBefore()` bidireccional: busca hacia adelante si no hay fecha hacia atrás
