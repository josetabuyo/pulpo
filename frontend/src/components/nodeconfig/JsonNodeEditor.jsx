import { useState, useRef, useCallback, useMemo } from 'react'

// ─── Sanitize control chars inside strings before parsing ─────────────────────

function sanitize(text) {
  const norm = text
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
  let inStr = false, escaped = false, result = ''
  for (let i = 0; i < norm.length; i++) {
    const ch = norm[i]
    if (escaped) { result += ch; escaped = false; continue }
    if (ch === '\\' && inStr) { escaped = true; result += ch; continue }
    if (ch === '"') { inStr = !inStr; result += ch; continue }
    if (inStr) {
      if (ch === '\n') { result += '\\n'; continue }
      if (ch === '\r') { result += '\\r'; continue }
      if (ch === '\t') { result += '\\t'; continue }
    }
    result += ch
  }
  return result
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function JsonNodeEditor({ config, schema, onChange }) {
  const stringify = c => JSON.stringify(c, null, 2)

  const [text, setText] = useState(() => stringify(config))
  const [parseError, setParseError] = useState(null)
  const lastExternal = useRef(config)
  const debounceTimer = useRef()

  const configJson = useMemo(() => stringify(config), [config])

  // Sync external config changes into textarea
  const prevConfigJson = useRef(configJson)
  if (configJson !== prevConfigJson.current) {
    prevConfigJson.current = configJson
    if (configJson !== stringify(lastExternal.current)) {
      lastExternal.current = config
      // Schedule update to avoid render-during-render
      Promise.resolve().then(() => {
        setText(configJson)
        setParseError(null)
      })
    }
  }

  const handleChange = useCallback((e) => {
    const value = e.target.value
    setText(value)
    clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      try {
        const parsed = JSON.parse(sanitize(value))
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setParseError('La config debe ser un objeto JSON')
          return
        }
        setParseError(null)
        lastExternal.current = parsed
        onChange(parsed)
      } catch (e) {
        setParseError(e.message)
      }
    }, 350)
  }, [onChange])

  // Cleanup debounce on unmount
  const cleanup = useRef()
  cleanup.current = () => clearTimeout(debounceTimer.current)

  const helpFields = (schema || []).filter(f => f.key)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

      {/* Textarea */}
      <textarea
        value={text}
        onChange={handleChange}
        spellCheck="false"
        autoComplete="off"
        autoCorrect="off"
        style={{
          width: '100%',
          boxSizing: 'border-box',
          minHeight: 200,
          resize: 'vertical',
          background: '#060d1a',
          color: '#e2e8f0',
          fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
          fontSize: 12,
          lineHeight: 1.6,
          border: `1px solid ${parseError ? '#7f1d1d' : '#1e293b'}`,
          borderRadius: 6,
          padding: '8px 10px',
          outline: 'none',
          transition: 'border-color 0.15s',
          tabSize: 2,
        }}
        onFocus={e => { if (!parseError) e.target.style.borderColor = '#334155' }}
        onBlur={e => { e.target.style.borderColor = parseError ? '#7f1d1d' : '#1e293b' }}
      />

      {/* Parse error */}
      {parseError && (
        <div style={{
          fontSize: 11, color: '#f87171', lineHeight: 1.4,
          padding: '4px 6px',
          background: '#1c0a0a',
          border: '1px solid #7f1d1d',
          borderRadius: 4,
        }}>
          ⚠ {parseError}
        </div>
      )}

      {/* Help panel — schema reference */}
      {helpFields.length > 0 && (
        <div style={{
          background: '#050c18',
          border: '1px solid #1e293b',
          borderRadius: 6,
          padding: '8px 10px',
          display: 'flex',
          flexDirection: 'column',
          gap: 5,
        }}>
          <div style={{
            fontSize: 9, color: '#334155', fontWeight: 700,
            letterSpacing: '0.12em', marginBottom: 2,
          }}>
            CAMPOS DISPONIBLES
          </div>
          {helpFields.map(f => (
            <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 10, color: '#60a5fa', fontFamily: 'monospace' }}>
                  {f.key}
                </span>
                <span style={{ fontSize: 9, color: '#334155' }}>{f.type}</span>
                {f.required && (
                  <span style={{ fontSize: 9, color: '#7f1d1d', fontWeight: 700 }}>req</span>
                )}
              </div>
              {(f.hint || f.label) && (
                <span style={{ fontSize: 10, color: '#475569', paddingLeft: 10 }}>
                  {f.hint || f.label}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
