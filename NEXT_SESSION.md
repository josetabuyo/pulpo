# NEXT_SESSION — Luganense: refactor grafo + imagen inteligente

## Contexto
Worktree: `bug-luganense` | Backend: `:8002` | `ENABLE_BOTS=false`
Arrancar: `./start.sh` desde la raíz de este worktree.

Doc de referencia: `management/BUG_LUGANENSE.md` (en master `_/`).

---

## Estado actual

- Todos los bugs originales resueltos
- MEJORA 1 (logs ricos) → en producción
- MEJORA 2 (imagen básica) → implementado, pendiente refactor antes de mergear
- feat-flow-ui → mergeado, el grafo descompuesto se verá en el visualizador

---

## Regla de esta sesión

Al terminar: **commit en bug-luganense → merge a master → push → restart backend de producción**.

---

## Tests antes de empezar

```bash
cd /Users/josetabuyo/Development/pulpo/bug-luganense/backend
/Users/josetabuyo/Development/pulpo/_/backend/.venv/bin/pytest tests/test_fetch_facebook_logs.py tests/test_summarizer.py -v
```
