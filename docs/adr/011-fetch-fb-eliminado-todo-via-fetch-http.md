# ADR-011: Se elimina `FetchFbNode` — todo consumo de APIs externas es `FetchHttpNode`

**Estado:** Aceptado — julio 2026. Corrige [ADR-010](010-noticias-http-directo-a-luganense.md)
(queda superado del todo, no solo parcialmente — ver más abajo).

## Contexto

ADR-010 reemplazó `fabi_driver.py` por `pulpo/tools/luganense_noticias.py`, un
cliente HTTP dedicado, y dejó `FetchFbNode` como nodo específico que lo
llamaba. En la misma sesión el usuario corrigió el rumbo una vez más: no
hacía falta ni un cliente Python dedicado ni un nodo dedicado — `FetchHttpNode`
(el nodo genérico que ya existía, usado por ejemplo contra
`/api/directorio/buscar`) cubre el caso de `/api/noticias` sin código nuevo,
solo configurando la URL en el editor de flows:

```json
{
  "url": "https://luganense.vercel.app/api/noticias?page_id=luganense&q={query}",
  "extract": "json",
  "extract_first_result_to_vars": true
}
```

El nodo dedicado a Facebook (`FetchFbNode`, antes acoplado primero a scraping
propio, después a Fabi en proceso, después a `luganense_noticias.py`) dejó de
tener una razón de ser: no hay ninguna transformación de datos ni lógica
específica de "Facebook" que un `FetchHttpNode` + template de URL no resuelva
igual de bien.

## Decisión

1. **Se borra `FetchFbNode` del todo**: `pulpo/graphs/nodes/fetch_fb.py`,
   `pulpo/graphs/nodes/test_fetch_fb.py`, y `pulpo/tools/luganense_noticias.py`
   (el cliente HTTP dedicado de ADR-010, también innecesario). Se saca del
   registro de nodos (`pulpo/graphs/node_types.py`, `pulpo/graphs/nodes/__init__.py`)
   y de la paleta del editor de flows (`frontend/src/store/flowStore.js`).
2. **El flow activo en prod se migró a mano.** El nodo `fetch_fb` de
   "Orquestador Vendedor Mejorado" (bot `luganense`, único flow activo que lo
   usaba) se reemplazó en el editor por un `FetchHttpNode` con la config de
   arriba, antes de borrar el tipo de nodo del código — evita el error de
   "tipo de nodo desconocido" en runtime. El flow viejo e inactivo
   ("Orquestador Vendedor", `d703b474-...`) se borró directamente de la DB, no
   se migró.
3. **`migrate_fetch_node_types()` (la migración one-shot de ADR-007, que
   separaba el nodo genérico viejo `"fetch"` en `fetch_http`/`fetch_fb` según
   `config.source`) se simplifica**: ahora cualquier nodo `"fetch"` que
   aparezca (no debería quedar ninguno, confirmado 0 en la DB actual) migra
   directo a `"fetch_http"`, sin bifurcación — `source: "facebook"` ya no
   significa nada especial.
4. **`pulpo/tools/` pierde su último rastro de Facebook.** Ya no hay ningún
   módulo en el repo que mencione Facebook fuera de comentarios/ADRs
   históricos y del contenido de las noticias en sí (los posts que trae
   `/api/noticias` siguen teniendo URLs `facebook.com/...` porque Fabi sigue
   scrapeando de ahí — eso es dato, no código).

## Consecuencias

- **Paginación de noticias queda pendiente y es tema de otra sesión.**
  `/api/noticias?page_id=luganense` hoy devuelve las 85 noticias sin
  `limit`/`offset` — confirmado contra prod el 2026-07-10. Para poder
  desarrollar un flow conversacional de noticias (traer de a 3, "che, contame
  más") hace falta que Luganense agregue paginación al endpoint. Se coordina
  como cualquier cambio de contrato cross-repo (mismo criterio que ADR-008):
  spec por escrito vía `las agent inject Luganense`, esperar confirmación
  antes de integrar nada.
- ADR-009 sigue parcialmente vigente (la parte de "Fabi es dueño del
  scraping") pero su §3/§4/§6 (Pulpo hablando con Fabi en proceso) ya no
  describen ningún código real — ni siquiera vía `luganense_noticias.py`.
  ADR-010 queda completamente superado por este documento: ni el cliente
  dedicado ni el nodo dedicado que proponía sobrevivieron el mismo día.
- Si en algún momento se justifica una integración real con el inbox de
  Facebook (mencionada como posibilidad futura, explícitamente fuera de
  alcance de este ADR), va a necesitar su propio diseño — no reflota
  `FetchFbNode` tal cual, distinto problema (leer mensajes entrantes, no
  buscar posts).
