# NEXT SESSION — feat-empresa-card

## Contexto
Worktree de desarrollo para **rediseño de UI: componente EmpresaCard unificado**.
Backend en :8001, Frontend en :5174. `ENABLE_BOTS=false` — usar simuladores.

## Estado: **LISTO PARA MERGE**

## Puertos
- Backend: `:8001` | Frontend: `:5174` | `ENABLE_BOTS=false`

## Arrancar
```bash
./start.sh  # desde /Users/josetabuyo/Development/pulpo/feat-empresa-card
```

---

## Objetivo

Crear un componente `EmpresaCard` unificado que funcione en dos contextos:

| Contexto | Ruta | Prop |
|---|---|---|
| Dashboard admin | `/dashboard` | `mode="admin"` |
| Portal empresa  | `/empresa`   | `mode="empresa"` |

**Lo más importante:** el admin habilita/deshabilita herramientas para cada empresa con un toggle. Las empresas solo ven las herramientas con `activa === true`.

---

## Estado del trabajo

### ✅ Ya hecho en este worktree:

**`frontend/src/components/EmpresaCard.jsx`** — componente nuevo completo:
- Tabs: Conexiones / Herramientas / Contactos / Configurar (solo empresa)
- `mode="admin"`: callbacks al padre para modales, drag&drop support, toggle tools
- `mode="empresa"`: self-contained — QR inline, add WA/TG inline, config inline
- `normalizeBot(bot)` helper exportado (convierte formato admin → canónico)
- SimChat integrado en admin+simMode+connected
- Toggle switch para habilitar/deshabilitar tools (solo admin)
- Sub-componentes: ConnectionRow, ToolRow, ToolForm, SummaryModal, ContactModal, EmpresaConfigTab, Toggle

**`frontend/src/index.css`** (primeras líneas):
- Import Google Fonts: DM Sans + JetBrains Mono
- CSS variables: `--brand`, `--bg`, `--surface`, `--border`, `--text-muted`, `--font-mono`, etc.
- Body font actualizado a DM Sans

### ✅ Completado en esta sesión:

**`frontend/src/index.css`** — CSS `ec-*` agregado al final

**`frontend/src/pages/DashboardPage.jsx`** — Actualizado:
- Import de `EmpresaCard` y `normalizeBot`
- Eliminados `PhoneRow`, `TelegramRow`, `STATUS_LABELS` (dead code)
- `bots.map` reemplazado por `<EmpresaCard mode="admin" ...>`
- `onDrop` actualizado para usar `.ec-card` en lugar de `.bot-block`

**`frontend/src/pages/EmpresaPage.jsx`** — Simplificado (1249 → ~165 líneas):
- Eliminados todos los componentes duplicados: `ConexionCard`, `ConfigView`, `HerramientasSection`, `ToolModal`, `SummaryModal`, `ContactModal`, `ContactosSection`, `ContactChat`, `connectAndPollEmpresa`
- `EmpresaDashboard` reescrito: solo carga datos y renderiza `<EmpresaCard mode="empresa" ...>`
- Se mantiene: `EmpresaLogin`, auth (login/logout/refresh), `empresaApi`, polling

**Testeado en simulador**:
- Dashboard admin: 3 EmpresaCards con tabs, badges WA/TG, SimChat, botones de acción ✅
- Portal empresa: tabs Conexiones/Herramientas/Contactos/Configurar, add canal inline ✅

### ⚠️ Pendiente conocido (backend):

`/api/empresas/{botId}/tools` retorna 401 desde modo admin — el backend acepta solo JWT empresa, no `x-password`. Las cards muestran "0 herramientas" pero no crashean.

**TODO backend**: agregar `x-password` admin auth a los routers de tools.

---

## CSS a agregar al FINAL de `index.css`

```css
/* ─── EmpresaCard ─────────────────────────────────────────────── */

.ec-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 20px;
  background: white;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
  transition: box-shadow .2s;
}
.ec-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.09); }
.ec-card.drag-over {
  outline: 2px dashed #7c3aed;
  outline-offset: -2px;
  background: #faf5ff;
}
.ec-header {
  background: linear-gradient(135deg, #faf5ff 0%, #f8fafc 100%);
  border-bottom: 1px solid #e8e0f0;
  padding: 14px 20px;
}
.ec-header-main { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.ec-header-info { flex: 1; min-width: 0; }
.ec-header-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 3px; }
.ec-bot-name { font-size: 15px; font-weight: 700; color: #1e1b4b; letter-spacing: -.3px; }
.ec-bot-id {
  font-size: 11px; color: #94a3b8; background: #f1f5f9;
  padding: 2px 8px; border-radius: 20px;
  font-family: var(--font-mono); letter-spacing: .2px;
}
.ec-sim-mode-badge {
  font-size: 10px; font-weight: 700; color: #92400e;
  background: #fef3c7; border: 1px solid #fcd34d;
  padding: 2px 8px; border-radius: 20px; letter-spacing: .5px;
}
.ec-bot-msg {
  font-size: 12px; color: #64748b; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 520px;
}
.ec-header-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.ec-status-dots { display: flex; gap: 5px; align-items: center; }
.ec-status-dot {
  width: 9px; height: 9px; border-radius: 50%; cursor: help; flex-shrink: 0;
  box-shadow: 0 0 0 2px white;
}
.ec-header-actions { display: flex; gap: 6px; }
.ec-tabs {
  display: flex; border-bottom: 1px solid #e8e8f0;
  background: white; padding: 0 16px; overflow-x: auto;
}
.ec-tab {
  display: flex; align-items: center; gap: 6px; padding: 10px 14px;
  font-size: 13px; font-weight: 500; color: #94a3b8;
  background: none; border-radius: 0;
  border-bottom: 2px solid transparent; margin-bottom: -1px; white-space: nowrap;
  transition: color .15s, border-color .15s;
}
.ec-tab:hover { color: #7c3aed; opacity: 1; }
.ec-tab--active { color: #7c3aed; border-bottom-color: #7c3aed; }
.ec-tab-badge {
  font-size: 10px; font-weight: 700; background: #ede9fe; color: #7c3aed;
  padding: 1px 6px; border-radius: 10px; min-width: 18px; text-align: center;
}
.ec-tab--active .ec-tab-badge { background: #7c3aed; color: white; }
.ec-content { padding: 0; }
.ec-section-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .7px; padding: 5px 20px 4px; border-bottom: 1px solid #f0f0f0;
}
.ec-section-label--wa { color: #059669; background: #f0fdf4; border-top: 1px solid #d1fae5; }
.ec-section-label--tg { color: #1d4ed8; background: #eff6ff; border-top: 1px solid #dbeafe; }
.ec-conn-row { border-bottom: 1px solid #f0f2f5; }
.ec-conn-row:last-of-type { border-bottom: none; }
.ec-conn-row.dragging { opacity: .4; }
.ec-conn-main { display: flex; align-items: center; padding: 10px 20px; gap: 10px; flex-wrap: wrap; }
.ec-chan-badge {
  display: inline-flex; align-items: center;
  font-size: 10px; font-weight: 700; padding: 2px 6px;
  border-radius: 4px; letter-spacing: .3px; flex-shrink: 0;
}
.ec-chan-badge--wa { background: #25d366; color: white; }
.ec-chan-badge--tg { background: #229ed9; color: white; }
.ec-conn-id {
  font-size: 13px; font-weight: 500; color: #1e293b;
  min-width: 110px; font-family: var(--font-mono); letter-spacing: -.3px;
}
.ec-conn-override { font-size: 11px; color: #94a3b8; font-style: italic; }
.ec-sim-badge {
  font-size: 10px; font-weight: 700; color: #92400e;
  background: #fef3c7; border: 1px solid #fde68a;
  padding: 2px 6px; border-radius: 4px; letter-spacing: .5px;
}
.ec-conn-actions { display: flex; gap: 6px; align-items: center; margin-left: auto; flex-wrap: wrap; }
.ec-conn-hint { font-size: 12px; color: #94a3b8; }
.ec-qr-inline {
  padding: 16px 20px; text-align: center;
  background: #faf5ff; border-top: 1px solid #ede9fe;
}
.ec-add-row {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 20px; border-top: 1px dashed #e8e8f0;
}
.ec-tools-summary { font-size: 12px; color: #94a3b8; margin-left: 4px; }
.ec-add-forms { border-top: 1px solid #e8e8f0; }
.ec-add-form-row { display: flex; gap: 12px; padding: 12px 20px; flex-wrap: wrap; }
.ec-tool-row {
  display: flex; align-items: center; padding: 12px 20px;
  border-bottom: 1px solid #f0f2f5; transition: background .15s;
}
.ec-tool-row:hover { background: #fafafc; }
.ec-tool-row--off { opacity: .6; }
.ec-tool-row:last-of-type { border-bottom: none; }
.ec-tool-main { display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 12px; }
.ec-tool-info { display: flex; align-items: center; gap: 8px; flex: 1; flex-wrap: wrap; }
.ec-tool-name { font-size: 14px; font-weight: 600; color: #1e293b; }
.ec-tool-type {
  font-size: 11px; color: #64748b; background: #f1f5f9;
  padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.ec-tool-scope { font-size: 12px; color: #94a3b8; }
.ec-tool-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ec-tool-status-badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 12px; }
.ec-tool-status-badge--on  { background: #ecfdf5; color: #059669; }
.ec-tool-status-badge--off { background: #f1f5f9; color: #94a3b8; }
.ec-toggle {
  width: 42px; height: 24px; border-radius: 12px;
  position: relative; cursor: pointer; border: none; padding: 0;
  transition: background .2s; flex-shrink: 0;
}
.ec-toggle--on  { background: #7c3aed; }
.ec-toggle--off { background: #cbd5e1; }
.ec-toggle:disabled { opacity: .4; cursor: not-allowed; }
.ec-toggle::after {
  content: ''; position: absolute; top: 3px;
  width: 18px; height: 18px; border-radius: 50%;
  background: white; transition: left .2s;
  box-shadow: 0 1px 3px rgba(0,0,0,.2);
}
.ec-toggle--on::after  { left: calc(100% - 21px); }
.ec-toggle--off::after { left: 3px; }
.ec-config-tab { padding: 20px; }
.ec-btn-active { background: #ede9fe !important; color: #7c3aed !important; }
.error { font-size: 13px; color: #c00; }
```

---

## ⚠️ Nota backend (importante)

Los endpoints de tools (`/api/empresas/{botId}/tools`, `/api/tools/{id}/toggle`) actualmente requieren **JWT empresa**. Para que el admin pueda manejar tools de una empresa, el backend debe aceptar también **`x-password`** en esos endpoints.

Si el backend no lo soporta todavía, las llamadas de tools en modo admin van a retornar 401. Diseñar el error para que sea evidente al usuario.

**TODO backend**: agregar `x-password` admin auth a los routers de tools.

---

## Lo que NO hacer
- No tocar `data/sessions/` (no existen — ENABLE_BOTS=false)
- No hacer push a origin (lo hace la sesión de `_`)
- No mergear directamente a master

## Merge
Cuando esté listo, avisarle a la sesión de `_` para merge + push.
