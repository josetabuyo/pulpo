# ADR-010: Pulpo consulta noticias directo por HTTP a Luganense — sin dependencia en tiempo de ejecución de Fabi

**Estado:** Aceptado — julio 2026. **Superado del todo por
[ADR-011](011-fetch-fb-eliminado-todo-via-fetch-http.md)** el mismo día: ni
siquiera hacía falta el cliente dedicado (`pulpo/tools/luganense_noticias.py`)
ni el nodo dedicado (`FetchFbNode`) que este documento proponía — el nodo
genérico `FetchHttpNode`, ya existente, cubre el caso completo solo
configurando la URL. Queda como registro histórico de por qué se sacó a Fabi
del camino en tiempo real (esa parte de la decisión sigue vigente); la
implementación concreta que describe abajo ya no existe en el código. Corrige
parcialmente [ADR-009](009-scraping-dominio-fabi.md) (queda vigente la parte
de "el scraping es dominio de Fabi", queda superada la parte de "Pulpo habla
con Fabi en proceso").

## Contexto

ADR-009 integró a Pulpo con Fabi en proceso: `pulpo/tools/fabi_driver.py`
importaba `fabi-lib` directo (editable, path local) y, en el camino lento del
nodo `FetchFbNode`, le pedía a Fabi que scrapeara Facebook en tiempo real
durante la conversación si no había cache fresca.

El usuario corrigió el rumbo (2026-07-09): Pulpo no tiene que saber que
Facebook existe, ni acoplarse en proceso a un servicio cuyo trabajo (scraping,
anti-baneo, cookies) es explícitamente ajeno a su responsabilidad. Fabi sigue
scrapeando e inyectando a Luganense por su cuenta, con su propio ciclo — pero
Pulpo no lo dispara ni lo espera nunca más. El resultado esperable para el
usuario final es el mismo (contenido "tipo Facebook" del barrio), pero servido
100% desde el dominio de Luganense, que ya lo expone.

## Decisión

1. **`pulpo/tools/luganense_noticias.py`** reemplaza a `fabi_driver.py`. Único
   método: `get_noticias(page_id, query, max_age) -> list[dict]`, un GET HTTP
   simple a `GET /api/noticias` de Luganense (mismo endpoint que ya existía
   desde [ADR-008](008-noticias-dominio-luganense.md), sin cambios de su
   lado). Fail-soft: `[]` si falla o no hay resultados, nunca levanta
   excepción — mismo criterio que `FetchHttpNode` contra cualquier API
   externa.
2. **Se borra el camino lento.** `FetchFbNode` ya no dispara scraping bajo
   ninguna circunstancia. Si Luganense no tiene nada fresco para una query,
   el nodo no tiene contexto para esa query — punto, sin Plan B. La rama
   "camino rápido / camino lento" de ADR-009 §4 deja de existir.
3. **Se borra `fabi-lib` como dependencia de Pulpo.** `pyproject.toml` ya no
   lista `fabi-lib` en `[project.dependencies]` ni tiene
   `[tool.uv.sources]` apuntando a `../../Fabi`. Se desinstaló de los dos
   venvs (`.venv/` dev, `.venv-pulpo/` prod). Pulpo no importa ningún módulo
   de `fabi` en ningún punto del código.
4. **Fabi no cambia nada de su lado.** Sigue scrapeando, sigue inyectando a
   `/api/noticias` (`POST`, público) por su propio ciclo (cron o lo que
   decida su implementación). Deja de tener consumidores en proceso, pero
   eso no afecta su funcionamiento — es una notificación de cortesía, no una
   coordinación necesaria.

## Consecuencias

- Pulpo pierde la capacidad de forzar un scraping fresco durante una
  conversación. Si Fabi está caído o desactualizado, Pulpo simplemente no
  tiene noticias frescas para esa query — fail-soft, sin fallback, igual que
  cualquier otro `FetchHttpNode` contra una API externa caída.
- Menos acoplamiento operativo: Pulpo ya no depende de que `fabi-lib` esté
  instalado editable desde un path local relativo (`../../Fabi`). Actualizar
  Fabi ya no requiere reinstalar nada en los venvs de Pulpo.
- `tests/e2e/luganense/test_noticias_persistencia.py` deja de tener sentido
  tal como estaba (probaba `fabi_driver` contra la librería real de Fabi) —
  se reemplazó por un test que pega un GET real a
  `luganense_noticias.get_noticias()` contra Luganense en producción, sin
  mocks. `test_ruta_noticias` (flow completo vía Telegram) no cambió — el
  flow es el mismo, solo cambió de dónde saca los datos.
- ADR-009 queda parcialmente superado: la parte de "Fabi es dueño del
  scraping" (§1, §2, §5) sigue siendo la decisión vigente; la parte de
  "Pulpo habla con Fabi en proceso" (§3, §4, §6) queda reemplazada por este
  documento.
