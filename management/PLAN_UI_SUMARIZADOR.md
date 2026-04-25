# Plan: UI del Sumarizador — Vista de conversación

## Objetivo

Crear una interfaz visual para leer el output del nodo sumarizador. Debe lucir como una conversación de WhatsApp: mensajes burbuja, timestamps, adjuntos descargables. Accesible desde dos lugares:
1. La lista de UIs del panel de empresa (al igual que otras UIs)
2. Desde el panel de config del nodo `summarize` en el editor de flows (acceso directo)

---

## Diseño visual

### Layout general

```
┌─────────────────────────────────────┐
│  [← Volver]  Conversación: +549...  │
│  Ivancho · gm_herreria              │
│                              [↓ MD] │
├─────────────────────────────────────┤
│                                     │
│  ── 18 mar 2026 ──                  │
│                                     │
│  ┌─────────────────────────┐        │
│  │ Hola, quería consultar  │ 14:32  │
│  │ por los precios...      │        │
│  └─────────────────────────┘        │
│                                     │
│        ┌──────────────────────────┐ │
│  14:35 │ [🎵 Audio 0:42]          │ │
│        │ "Mirá lo que pasa es que │ │
│        │ necesito unas 20 barras" │ │
│        └──────────────────────────┘ │
│                                     │
│  ┌──────────────────────────────┐   │
│  │ 📄 catálogo.pdf · 120 kB    │   │
│  │              [Descargar ↓]  │   │
│  └──────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
```

### Reglas visuales

- Mensajes **entrantes** (del contacto): alineados a la izquierda, burbuja oscura
- Mensajes **salientes** (del bot/operador): alineados a la derecha, burbuja verde
- **Separadores de fecha** entre bloques de mensajes de días distintos
- **Audios**: ícono de onda de audio + duración + transcripción colapsable
- **Documentos**: ícono de tipo de archivo + nombre + tamaño + botón Descargar
- **Imágenes** (futuro): thumbnail inline

---

## Fuente de datos

El sumarizador ya genera archivos `.md` en `data/summaries/{empresa_id}/{contact_phone}.md`. La UI necesita parsear ese MD o consumir un endpoint JSON.

### Opción A — Parsear el MD en el frontend
- El endpoint devuelve el MD crudo
- El frontend lo parsea a mensajes estructurados

### Opción B — Endpoint JSON estructurado (recomendada)
El backend parsea el MD y devuelve un array de mensajes:
```json
[
  {
    "type": "text",
    "direction": "in",
    "timestamp": "2026-03-18T14:32:00",
    "content": "Hola, quería consultar por los precios del hierro"
  },
  {
    "type": "audio",
    "direction": "in",
    "timestamp": "2026-03-18T14:35:00",
    "duration": "0:42",
    "transcription": "Mirá lo que pasa es que necesito unas 20 barras..."
  },
  {
    "type": "document",
    "direction": "in",
    "timestamp": "2026-03-20T16:59:00",
    "filename": "catalogo.pdf",
    "size": "120 kB",
    "download_url": "/api/summaries/gm_herreria/5491155612767/docs/catalogo.pdf"
  }
]
```

---

## Descarga de adjuntos

Los archivos adjuntos descargados por el sumarizador viven en:
```
data/summaries/{empresa_id}/docs/{contact_phone}/{filename}
```

Endpoint de descarga:
```
GET /api/summaries/{empresa_id}/{contact_phone}/docs/{filename}
```
- Auth: misma que el resto de endpoints de empresa
- Sirve el archivo con `Content-Disposition: attachment`
- Misma UX que WhatsApp: click en el nombre del archivo → descarga inmediata

---

## Acceso desde el nodo summarize

Cuando el nodo `summarize` está seleccionado en el editor de flows, el panel de config muestra un botón **"Ver conversación →"** que abre la UI directamente para el contact_phone asociado al flow activo.

Para implementarlo: en `NodeConfigPanel`, cuando el tipo de nodo es `summarize`, renderizar un link adicional debajo de la config.

---

## Fases de implementación

### Fase 1 — Vista básica de texto (MVP)
- Endpoint `GET /api/summaries/{empresa_id}/{contact_phone}` → devuelve JSON estructurado
- Componente `SummaryView.jsx` con burbujas de texto
- Separadores de fecha
- Accesible desde la lista de UIs del panel de empresa

### Fase 2 — Audios y documentos
- Burbujas de audio con transcripción colapsable
- Burbujas de documento con botón descargar
- Endpoint de descarga de adjuntos

### Fase 3 — Acceso desde el nodo
- Botón "Ver conversación →" en `NodeConfigPanel` cuando el nodo es `summarize`
- Selector de contacto si el flow no tiene contact_phone fijo

### Fase 4 — Botón "Generar informe IA"
- Llama al endpoint de procesamiento IA (Fase 4 de PLAN_TOOL_SUMARIZADORA.md)
- Muestra el informe estructurado en una sección separada dentro de la misma UI

---

## Archivos a crear/modificar

```
backend/api/summarizer.py              — agregar endpoint JSON + endpoint descarga
frontend/src/components/SummaryView.jsx — componente nuevo (vista burbuja)
frontend/src/components/NodeConfigPanel.jsx — botón "Ver conversación" en nodo summarize
frontend/src/components/EmpresaCard.jsx — punto de entrada desde lista UIs (ya hay "Ver resúmenes")
```

---

## Estado

- [x] Fase 1 — Vista básica burbujas de texto
- [x] Fase 2 — Audios + documentos + descarga
- [x] Fase 3 — Acceso desde panel del nodo summarize
- [ ] Fase 4 — Botón generar informe IA

## Implementado (sesión 2026-04-16/17)

### Backend (`backend/api/summarizer.py`)
- `GET /summarizer/{empresa_id}` → devuelve `{contacts: [{phone, name}], path: "/abs/path/..."}`
- `GET /summarizer/{empresa_id}/{contact_phone}/messages` → inbound (.md parseado) + outbound (DB), ordenados por timestamp. Parsea `"Nombre: contenido"` en grupo → campo `sender` separado.
- `POST /summarizer/{empresa_id}/{contact_phone}/sync` → re-sync seguro por contacto con filtrado de ruido
- `GET /summarizer/{empresa_id}/{contact_phone}/docs/{filename}` → descarga adjunto

### Frontend
- `SummaryView.jsx` — burbujas in (izq) / out (der), separadores de día, AudioBubble, DocumentBubble, botón ↻ sync, botón ↓ MD
- `SummaryContactList.jsx` — muestra nombre resuelto desde agenda, avatar con iniciales
- `NodeConfigPanel.jsx` — nodo summarize muestra path absoluto (fetched del backend) + botón "Ver resúmenes" que cambia a tab UIs
- `EmpresaCard → FlowList → FlowEditor → NodeConfigPanel` — cadena `onGoToUIs` prop

### Bugs corregidos
- `group_sender` en FlowState: audios de grupo ya no saltean transcripción por el prefijo "Nombre: "
- `list_contacts()` excluye archivos `.bak.md`
- Re-trigger histórico (`POST /empresas/{id}/flows/{flow_id}/replay`) con `from_delta_sync=True`
- `.md` de SIGIRH reordenado por fecha (tenía mensajes desordenados)

### Pendiente / conocido
- Duplicados en DB: el polling guarda algunas veces el mismo mensaje dos veces con el mismo timestamp (10 grupos detectados en la_piquiteria)
- Audios `[audio — sin blob]` históricos: blob expiró en WA Web, irrecuperables
- Fase 4: botón "Generar informe IA" no implementado
