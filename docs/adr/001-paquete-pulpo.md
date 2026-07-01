# ADR-001: El backend vive en el paquete pip `pulpo`

**Estado:** Aceptado — implementado en producción (2026-06-30)

## Contexto

Hasta junio 2026, el backend era un directorio flat `backend/` con imports relativos
(`from db import`, `from config import`, etc.). Esto hacía imposible:
- instalar el código como dependencia
- testear módulos individuales sin levantar el servidor completo
- razonar sobre qué era público vs interno

## Decisión

Todo el código de backend vive en el paquete `pulpo/` instalable via `uv`.
El paquete se instala en modo editable (`uv pip install -e .`) para que launchd
use siempre el código fuente de master sin pasos de build.

```
pulpo/
  business/     # lógica de dominio (flows, contactos, sim, wavi)
  connections/  # drivers de canal (telegram, wavi, teli)
  core/         # db, config, state, lifespan
  graphs/       # compilador de flows + nodos
  interfaces/   # las 4 interfaces públicas (ver ADR-002)
  tools/        # transcripción, browser
```

## Consecuencias

- **Imports absolutos siempre:** `from pulpo.core.db import log_message`, nunca relativos entre módulos de primer nivel.
- **`backend/` está muerto:** no se crea ni se modifica. El directorio fue eliminado del repo en el commit de limpieza (2026-07-01).
- **Agregar dependencias:** `uv add <paquete>` desde la raíz de `_/`. Esto actualiza `pyproject.toml` y `uv.lock`.
- **Launchd usa `.venv-pulpo/`** con instalación editable apuntando a `_/`. No requiere reinstalar al hacer cambios en el código fuente.
