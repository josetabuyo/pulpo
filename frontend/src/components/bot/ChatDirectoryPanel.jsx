/**
 * Editor de la config del directorio "conectar directo" (comercios/servicios
 * hoy, ver web/lib/business/chat-directory-types.ts) -- primera versión:
 * editor JSON crudo + validación al guardar + "Probar búsqueda" contra el
 * endpoint real de cada sección para verificar items_path/item_map sin
 * adivinar. Un form-builder visual por campo es un paso posterior, no
 * bloqueante para el release.
 */
import { useEffect, useState } from 'react'
import { chatDirectoryApi, chatApi } from '../../lib/chatApi.js'

const PLACEHOLDER_EXAMPLE = `{
  "version": 1,
  "enabled": true,
  "title": "Directorio",
  "sections": [
    {
      "id": "comercios",
      "label": "Comercios",
      "search_placeholder": "Buscar comercio…",
      "empty_query": "search",
      "source": {
        "method": "GET",
        "url": "https://cliente.example.com/api/directorio/buscar?q={{q}}&tipo=comercios",
        "items_path": "results",
        "item_map": { "id": "id", "title": "nombre", "subtitle": "rubro", "meta": "direccion" },
        "limit": 30
      },
      "connect": {
        "label": "Conectar",
        "fields": [],
        "confirm_text": "¿Conectarte con {{item.title}}?",
        "success_text": "Listo, ya avisamos a {{item.title}}.",
        "lead": {
          "method": "POST",
          "url": "https://cliente.example.com/api/actividad-comercial",
          "success_codes": [200, 201],
          "body": {
            "tipo": "comercio_confirmado",
            "payload": { "comercio": "{{item.title}}" },
            "contact_id": "{{contact.id}}",
            "contact_channel": "{{contact.channel}}"
          }
        }
      }
    }
  ]
}`

function TrySearch({ botId, chatId, sections }) {
  const [sectionId, setSectionId] = useState(sections[0]?.id || '')
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!sectionId && sections[0]) setSectionId(sections[0].id)
  }, [sections, sectionId])

  async function run() {
    if (!sectionId) return
    setLoading(true)
    const res = await chatApi.directorySearch(botId, chatId, sectionId, q)
    setLoading(false)
    setResult(res)
  }

  if (sections.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <select value={sectionId} onChange={e => setSectionId(e.target.value)} style={{ fontSize: 12 }}>
          {sections.map(s => <option key={s.id} value={s.id}>{s.id}</option>)}
        </select>
        <input type="text" value={q} onChange={e => setQ(e.target.value)} placeholder="q (vacío = listar todo, si la config lo permite)"
          style={{ flex: 1, fontSize: 12 }} />
        <button type="button" className="btn-sm" onClick={run} disabled={loading}>{loading ? 'Buscando...' : 'Probar búsqueda'}</button>
      </div>
      {result && (
        <pre style={{ fontSize: 11, background: 'var(--surface-2)', padding: 8, borderRadius: 6, maxHeight: 220, overflow: 'auto', margin: 0 }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function ChatDirectoryPanel({ botId, chatId, apiCall }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)
  const [parsedSections, setParsedSections] = useState([])

  async function load() {
    setLoading(true)
    const data = await chatDirectoryApi.get(apiCall, botId, chatId).catch(() => null)
    setText(JSON.stringify(data ?? { version: 1, enabled: false, sections: [] }, null, 2))
    setParsedSections(data?.sections ?? [])
    setLoading(false)
  }

  useEffect(() => { load() }, [botId, chatId])

  async function handleSave() {
    setErr('')
    setSaved(false)
    let parsed
    try {
      parsed = JSON.parse(text)
    } catch {
      setErr('JSON inválido')
      return
    }
    setSaving(true)
    const res = await chatDirectoryApi.save(apiCall, botId, chatId, parsed).catch(() => null)
    setSaving(false)
    if (!res || res.detail) {
      setErr(res?.detail || 'Error al guardar')
      return
    }
    setParsedSections(res.sections ?? [])
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  if (!chatId) {
    return <div className="empty" style={{ padding: '8px 0', fontSize: 13 }}>Guardá el chat primero para configurar el directorio.</div>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Directorio (conectar directo)</span>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-subtle)', marginTop: 0 }}>
        Camino paralelo al chat: rail izquierdo con secciones configurables (comercios, servicios, ...),
        cada una con su endpoint de catálogo y su llamado de lead al conectar. Config genérica, sirve para cualquier cliente.
      </p>

      {loading ? (
        <div className="empty" style={{ padding: '8px 0' }}>Cargando...</div>
      ) : (
        <>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            rows={16}
            placeholder={PLACEHOLDER_EXAMPLE}
            style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
            <button type="button" className="btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
            </button>
            {saved && <span style={{ color: 'var(--success)', fontSize: 12 }}>Guardado ✓</span>}
            {err && <span style={{ color: 'var(--danger)', fontSize: 12 }}>{err}</span>}
          </div>

          <TrySearch botId={botId} chatId={chatId} sections={parsedSections} />
        </>
      )}
    </div>
  )
}
