# Plan: Import de contactos sugeridos desde WA Web

## Problema

El botón "Importar desde WA" abre el panel "Nuevo chat" y scrollea buscando números de teléfono en `span[title]`. Solo funciona para **contactos no guardados** (donde WA muestra el número directamente). Para contactos guardados (con nombre en la agenda), WA Web no expone el número en el DOM del panel "Nuevo chat" — solo muestra el nombre.

Resultado: se importan ~7 contactos en lugar del total de la agenda.

## Causa raíz

WA Web virtualiza la lista de "Nuevo chat" y para contactos con nombre en la agenda, el `span[title]` contiene el nombre, no el teléfono. El número nunca aparece en el DOM de ese panel. Esta es una limitación de WA Web by design.

## Solución propuesta

**Usar solo nombres como identificadores — sin teléfonos en el import.**

El sistema ya soporta nombres en `contact_filter.included/excluded`. `_resolve_filter_value()` resuelve nombre → teléfono en runtime comparando contra `contact_channels`. Si el contacto no está registrado todavía, la lógica de `include_unknown` cubre el resto.

### Modelo de datos

Tabla nueva `contact_suggestions`:
```sql
CREATE TABLE contact_suggestions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id TEXT NOT NULL,
    name      TEXT,          -- nombre del contacto (puede ser nulo si solo se tiene teléfono)
    phone     TEXT,          -- teléfono (puede ser nulo si WA no lo expone para ese contacto)
    source    TEXT,          -- 'wa_import' | 'message_history'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(empresa_id, name, phone)
);
```

Regla: al menos uno de `name` o `phone` debe estar presente.

### Cambios necesarios

1. **Crear tabla `contact_suggestions`** en `db.py` con migración automática al arrancar.

2. **Refactorizar `_COLLECT_CONTACTS_JS`** — recolectar todos los `span[title]` válidos del panel "Nuevo chat":
   - Si el título parece teléfono → `{phone: valor, name: null}`
   - Si el título parece nombre → `{name: valor, phone: null}`
   - Si hay un par teléfono+nombre adyacentes → `{phone: ..., name: ...}`
   - Filtrar junk con `isJunk()` existente

3. **Actualizar `_scrape_wa_contacts(page)`** — scroll exhaustivo de toda la agenda, devuelve `list[{"name": str|null, "phone": str|null}]`.

4. **Actualizar endpoint POST import** — insertar en `contact_suggestions`. Para "Nuevo chat" carga nombres. Para historial de mensajes carga phone+name cuando hay número real.

5. **Actualizar `GET /bots/{bot_id}/contacts/suggested`** — leer de `contact_suggestions`. Responde `[{name, phone}]`.

6. **Actualizar `DELETE /empresa/{bot_id}/suggested-contacts`** — borrar de `contact_suggestions`.

7. **`_resolve_filter_value()` ya acepta nombre o teléfono indistintamente** — sin cambios.

8. **`EmpresaCard.jsx`** — mostrar nombre si existe, teléfono como dato adicional. Sin cambios estructurales.

### Flujo esperado

- Usuario aprieta "Importar desde WA"
- Se scrollea "Nuevo chat" **exhaustivamente** — todos los contactos de la agenda, no solo los ~7 con teléfono visible
- Los contactos guardados (con nombre) se guardan con `name` solamente
- Los contactos sin guardar (número visible) se guardan con `phone` y opcionalmente `name`
- El historial de mensajes aporta `phone + name` para contactos que ya escribieron
- En `ContactFilterPicker` el usuario ve el nombre reconocible; si solo hay teléfono, muestra el teléfono
- Al ejecutar el flow, `_resolve_filter_value("María García", empresa_id)` busca en `contact_channels`
- Si el nombre no está en `contact_channels` pero está como sugerido → se trata como desconocido (`include_unknown`)

## Estado

- [ ] Crear tabla `contact_suggestions`
- [ ] Refactorizar JS de scraping para recolectar nombres (no teléfonos)
- [ ] Actualizar endpoints de sugeridos
- [ ] Migrar datos existentes (limpiar [wa-contact-import] en messages)
- [ ] Actualizar EmpresaCard si es necesario

## Notas

- `bot_test` y `la_piquiteria` usan la misma conexión (67) — no tienen impacto en este plan
- headless=False en `state.py` fue puesto para debug del import; revertir a `True` una vez validado
