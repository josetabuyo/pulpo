# Bug Fix: full-sync no captura mensajes recientes (se detiene a mitad del historial)

## Contexto
Worktree: `_` (master, producción)
Empresa: `la_piquiteria`
Grupo WA: `Desarrollo SIGIRH  2025`

## El bug

`/api/full-sync` lanza `scrape_full_history` en background. El scraper scrollea el historial del chat hacia arriba (mensajes viejos), pero **se detiene antes de capturar los mensajes más recientes**.

Resultado actual del .md: cubre hasta **2026-03-17 18:26** (martes).
El chat real tiene mensajes del **miércoles 18/3, jueves 19/3 y viernes 20/3** que no aparecen.

### Mensajes faltantes (visibles en captura de pantalla WA Web)
- **Miércoles 18/3**: Florencia comparte video IA (21:36), conversación de acceso Figma
- **Jueves 19/3**: Fabian sube archivo SQL "Agregar Módulo en menú principal.sql" (16:59)
- **Viernes 20/3 (ayer)**: Fabian sube PPTX "Pantallas Telefono y Mails en Datos Personales de la Web.pptx" (08:47) + mensaje con código SQL (14:27)

## Archivos clave

- `backend/automation/whatsapp.py` → función `scrape_full_history`
  - Part A: scrape de textos (scroll hacia arriba)
  - Part B: captura de audios
- `backend/api/whatsapp.py` → endpoint `/api/full-sync` que llama `scrape_full_history`

## Root cause probable

`scrape_full_history` hace scroll hacia arriba hasta encontrar el principio del chat,
pero **no scrollea de vuelta hacia abajo** para capturar lo más reciente antes del fondo.
O bien tiene un límite de mensajes / iteraciones que corta antes del final.

Otra posibilidad: el scroll llega hasta un punto y WA Web virtualiza los mensajes
más recientes (los saca del DOM), y el scraper no los vuelve a encontrar.

## Plan

1. Correr los tests: `cd backend && .venv/bin/pytest tests/ -v`
2. Leer `scrape_full_history` en `backend/automation/whatsapp.py`
   — buscar cómo se hace el scroll, cuándo para, cómo detecta el fin
3. Verificar si hay un scroll hacia abajo al final que capture los mensajes recientes
4. Fix: asegurar que después del scroll up completo, se scrollee back to bottom
   y se capture también los mensajes del fondo (los más recientes)
5. Probar con full-sync: `curl -X POST http://localhost:8000/api/full-sync -H "x-password: MonoLoco"`
6. Verificar que el .md incluya mensajes del 18/3, 19/3, 20/3
7. Re-correr `wa_decrypt.py` si los audios vuelven a quedar como "sin blob":
   `cd backend && GROQ_API_KEY=$(grep GROQ .env | cut -d= -f2) .venv/bin/python tools/wa_decrypt.py`
8. Commit + push

## Notas importantes

- El re-sync de la UI (`↺ Re-sync` en el dashboard) NO hace full-sync — solo el listener
- El full-sync real es solo vía API: `POST /api/full-sync` con header `x-password: MonoLoco`
- Los audios PTT del grupo tienen mediaKeys y directPaths en `backend/tools/wa_decrypt.py`
  → Si el full-sync regenera los "sin blob", correr ese script (lee IndexedDB de WA Web)
- El .md del grupo vive en `data/summaries/la_piquiteria/Desarrollo SIGIRH  2025.md`
  (nombre con non-breaking spaces `\xa0`)
- Backend prod en `http://localhost:8000`, password `MonoLoco`
