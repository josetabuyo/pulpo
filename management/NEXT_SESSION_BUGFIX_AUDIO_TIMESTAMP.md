# Bug Fix: Timestamp incorrecto en audios del scrape

## Contexto
Worktree: `_` (master, producción)
Empresa afectada: `la_piquiteria`
Grupo WA: `Desarrollo SIGIRH  2025`

## El bug

El audio de **Fabian Miranda** a las **11:41 a.m. del martes 17/3/2026** aparece en el resumen con fecha **2026-03-16** (lunes) en vez de **2026-03-17** (martes).

### Evidencia en el .md actual
```
## 2026-03-16 11:41           ← ❌ fecha incorrecta (debería ser 2026-03-17)
**[audio]**  Chicos, voy manejando y se me ocurren estas preguntas...
```

### Evidencia visual (WA Web screenshot)
- El último mensaje del lunes (16/3) es Santiago Eliges: "No entendí jaja pero mañana lo vemos" a las **10:28 p.m.**
- Luego aparece el separador de día **"martes"**
- Luego el audio de Fabian Miranda a las **11:41 a.m.** — este ya es del martes 17/3

El audio está en el resumen pero con el día equivocado: dice 16/3 cuando es 17/3.

## Root cause probable

`scrape_full_history` tiene dos partes:
- **Part A** (texto): extrae timestamps de `data-pre-plain-text` → incluye fecha completa `[11:46 a. m., 17/3/2026]`
- **Part B** (audio): extrae timestamps de un selector visual como `span[data-testid="msg-time"]` → puede devolver solo `"11:41 a. m."` sin fecha

Cuando el parser de Part B no puede extraer la fecha completa, usa la fecha de un mensaje anterior (16/3) o algún fallback, resultando en 16/3 11:41 en vez de 17/3 11:41.

## Archivos clave
- `backend/automation/whatsapp.py` → función `scrape_full_history`, Part B (audio capture durante scroll)
- Buscar dónde se construye el `timestamp` del dict de audio en el array de mensajes Part B

## Plan
1. Correr los tests existentes: `cd backend && .venv/bin/pytest tests/ -v`
2. Leer la sección Part B de `scrape_full_history` — buscar cómo se asigna `timestamp` a los audios
3. Identificar si el parser usa `data-pre-plain-text` (tiene fecha) o selector alternativo (solo hora)
4. Fix: para audios sin fecha explícita, inferir la fecha del `data-pre-plain-text` del contenedor del mensaje, o del mensaje de texto anterior con fecha conocida
5. Agregar test en `test_summarizer.py` que verifica que el timestamp del audio es correcto
6. Correr full-sync real: `curl -X POST http://localhost:8000/api/full-sync -H "x-password: MonoLoco"`
7. Verificar en el .md que `2026-03-17 11:41` aparece en el lugar correcto (después de Santiago a las 10:28 del 16/3)
8. Commit + push

## Notas
- Backend en prod corre en `http://localhost:8000` con `ADMIN_PASSWORD=MonoLoco`
- El WA bot usa el perfil Chrome en `data/sessions/5491155612767/profile/` — NO tocar
- El resumen vive en `data/summaries/la_piquiteria/Desarrollo SIGIRH  2025.md`
- Para re-generar el resumen completo: borrar el .md y correr full-sync (el código ya llama `clear_contact` automáticamente)
