import { useState, useRef, useCallback, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { json } from '@codemirror/lang-json'
import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting, syntaxTree } from '@codemirror/language'
import { autocompletion } from '@codemirror/autocomplete'
import { tags } from '@lezer/highlight'

// ─── Triple-quote strings (estilo Python) — legibles, sin \n literales ────────
// """texto\nmultilínea""" se convierte a un string JSON válido antes de parsear.
// No soporta """ dentro del contenido (misma limitación que Python).

function convertTripleQuotes(text) {
  return text.replace(/"""([\s\S]*?)"""/g, (_, content) => JSON.stringify(content))
}

// Serializa un valor con el mismo formato que JSON.stringify(v, null, 2),
// salvo que los strings con saltos de línea reales se emiten como """...""".
function stringifyPretty(value, indent = 0) {
  const pad = '  '.repeat(indent)
  const padInner = '  '.repeat(indent + 1)
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'number' || typeof value === 'boolean') return JSON.stringify(value)
  if (typeof value === 'string') {
    if (value.includes('\n') && !value.includes('"""')) {
      return `"""${value}"""`
    }
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    const items = value.map(v => padInner + stringifyPretty(v, indent + 1))
    return '[\n' + items.join(',\n') + '\n' + pad + ']'
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value)
    if (keys.length === 0) return '{}'
    const items = keys.map(k => padInner + JSON.stringify(k) + ': ' + stringifyPretty(value[k], indent + 1))
    return '{\n' + items.join(',\n') + '\n' + pad + '}'
  }
  return JSON.stringify(value)
}

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

// ─── Autocomplete: sugerir claves del schema como PropertyName ────────────────

function makeKeyCompletionSource(schema) {
  const keys = (schema || []).filter(f => f.key).map(f => ({
    label: f.key,
    detail: f.type,
    info: f.hint || f.label || undefined,
    type: 'property',
  }))

  return (context) => {
    if (keys.length === 0) return null

    const tree = syntaxTree(context.state)
    const node = tree.resolveInner(context.pos, -1)
    const inPropertyName = node.type.name === 'PropertyName'
    const word = context.matchBefore(/"[\w-]*/)

    if (!inPropertyName && !(word && node.type.name !== 'String')) return null
    if (!word) return null

    return {
      from: word.from,
      options: keys.map(k => ({ ...k, apply: `"${k.label}"` })),
      filter: true,
      validFor: /^"[\w-]*$/,
    }
  }
}

// ─── Tema CodeMirror — paleta slate del panel de config ───────────────────────

const pulpoHighlight = HighlightStyle.define([
  { tag: tags.propertyName, color: '#60a5fa' },
  { tag: tags.string, color: '#4ade80' },
  { tag: tags.number, color: '#fbbf24' },
  { tag: tags.bool, color: '#f472b6' },
  { tag: tags.null, color: 'var(--text-muted)' },
  { tag: tags.punctuation, color: 'var(--text-muted)' },
  { tag: tags.brace, color: 'var(--text-subtle)' },
  { tag: tags.squareBracket, color: 'var(--text-subtle)' },
])

const pulpoTheme = EditorView.theme({
  '&': {
    backgroundColor: 'var(--bg)',
    color: 'var(--text)',
    fontSize: '12px',
    fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
  },
  '.cm-content': {
    caretColor: '#60a5fa',
    padding: '8px 0',
  },
  '.cm-cursor': {
    borderLeftColor: '#60a5fa',
  },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground': {
    backgroundColor: '#1e3a5f !important',
  },
  '.cm-gutters': {
    backgroundColor: 'var(--bg)',
    color: 'var(--border-strong)',
    border: 'none',
    borderRight: '1px solid var(--surface-2)',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'var(--bg)',
  },
  '.cm-activeLine': {
    backgroundColor: 'var(--bg)',
  },
  '.cm-foldPlaceholder': {
    backgroundColor: 'var(--surface-2)',
    color: 'var(--text-muted)',
    border: 'none',
  },
  '.cm-matchingBracket': {
    backgroundColor: '#1e3a5f',
    outline: '1px solid #60a5fa',
  },
  '.cm-tooltip': {
    backgroundColor: 'var(--bg)',
    border: '1px solid var(--border-strong)',
    borderRadius: '4px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
  },
  '.cm-tooltip-autocomplete': {
    '& > ul': {
      fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
      fontSize: '11px',
    },
    '& > ul > li': {
      padding: '4px 8px',
      color: 'var(--text)',
    },
    '& > ul > li[aria-selected]': {
      backgroundColor: '#1e3a5f',
      color: '#60a5fa',
    },
  },
  '.cm-completionLabel': {
    color: '#60a5fa',
  },
  '.cm-completionDetail': {
    color: 'var(--text-muted)',
    fontStyle: 'normal',
    marginLeft: '8px',
  },
  '.cm-completionIcon-property': {
    '&::after': { content: "'◆'" },
    color: '#4ade80',
  },
})

const baseExtensions = [json(), pulpoTheme, syntaxHighlighting(pulpoHighlight), EditorView.lineWrapping]

// ─── Component ────────────────────────────────────────────────────────────────

const MIN_EDITOR_HEIGHT = 100
const MAX_EDITOR_HEIGHT = 700
const DEFAULT_EDITOR_HEIGHT = 200
const MIN_AYUDA_HEIGHT = 90

export default function JsonNodeEditor({ config, schema, onChange }) {
  const stringify = c => stringifyPretty(c)

  const [text, setText] = useState(() => stringify(config))
  const [parseError, setParseError] = useState(null)
  const lastExternal = useRef(config)
  const debounceTimer = useRef()

  const [editorHeight, setEditorHeight] = useState(DEFAULT_EDITOR_HEIGHT)
  const resizingRef = useRef(false)
  const [copiedId, setCopiedId] = useState(null)
  const copiedTimer = useRef()

  const handleSplitResizeStart = useCallback((e) => {
    e.preventDefault()
    resizingRef.current = true
    const startY = e.clientY
    const startHeight = editorHeight
    function handleMouseMove(ev) {
      if (!resizingRef.current) return
      const delta = ev.clientY - startY
      setEditorHeight(Math.min(MAX_EDITOR_HEIGHT, Math.max(MIN_EDITOR_HEIGHT, startHeight + delta)))
    }
    function handleMouseUp() {
      resizingRef.current = false
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }, [editorHeight])

  function copyToClipboard(value, id) {
    if (value === undefined || value === null) return
    navigator.clipboard.writeText(String(value))
    setCopiedId(id)
    clearTimeout(copiedTimer.current)
    copiedTimer.current = setTimeout(() => setCopiedId(null), 1200)
  }

  const configJson = useMemo(() => stringify(config), [config])

  const extensions = useMemo(() => {
    const completionSource = makeKeyCompletionSource(schema)
    return [
      ...baseExtensions,
      autocompletion({
        override: [completionSource],
        activateOnTyping: true,
        icons: true,
      }),
    ]
  }, [schema])

  // Sync external config changes into el editor
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

  const handleChange = useCallback((value) => {
    setText(value)
    clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      try {
        const parsed = JSON.parse(sanitize(convertTripleQuotes(value)))
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

  const helpFields = (schema || []).filter(f => f.key)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minHeight: 0 }}>

      {/* Editor */}
      <div
        style={{
          borderRadius: 6,
          border: `1px solid ${parseError ? 'var(--danger-dim)' : 'var(--surface-2)'}`,
          overflow: 'hidden',
          transition: 'border-color 0.15s',
          height: editorHeight,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <CodeMirror
          value={text}
          onChange={handleChange}
          extensions={extensions}
          theme="none"
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            bracketMatching: true,
            closeBrackets: true,
            autocompletion: false,
            highlightActiveLine: true,
            highlightSelectionMatches: false,
            searchKeymap: false,
          }}
          style={{ flex: 1, height: '100%', overflow: 'auto' }}
        />
      </div>

      {/* Parse error */}
      {parseError && (
        <div style={{
          fontSize: 11, color: 'var(--danger)', lineHeight: 1.4,
          padding: '4px 6px',
          background: 'var(--danger-dim)',
          border: '1px solid var(--danger-dim)',
          borderRadius: 4,
        }}>
          ⚠ {parseError}
        </div>
      )}

      {/* Help panel — schema + opciones, click para copiar al portapapeles */}
      {helpFields.length > 0 && (
        <>
          {/* Resize handle — arrastra el límite entre editor y ayuda */}
          <div
            onMouseDown={handleSplitResizeStart}
            title="Arrastrar para redimensionar"
            style={{
              height: 6,
              margin: '-4px 0',
              cursor: 'row-resize',
              position: 'relative',
              zIndex: 5,
              flexShrink: 0,
            }}
          />

          <div style={{
            background: 'var(--bg)',
            border: '1px solid var(--surface-2)',
            borderRadius: 6,
            padding: '8px 10px',
            flex: 1,
            minHeight: MIN_AYUDA_HEIGHT,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}>
            <div style={{
              fontSize: 9, color: 'var(--border-strong)', fontWeight: 700,
              letterSpacing: '0.12em',
            }}>
              AYUDA
            </div>
            {helpFields.map(f => {
              const fieldId = `field:${f.key}`
              return (
                <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div
                    onClick={() => copyToClipboard(f.key, fieldId)}
                    title="Clic para copiar el nombre del campo"
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                      padding: '2px 4px', margin: '-2px -4px', borderRadius: 4,
                      background: copiedId === fieldId ? 'var(--success-dim)' : 'transparent',
                    }}
                  >
                    <span style={{
                      fontSize: 10, fontFamily: 'monospace',
                      color: copiedId === fieldId ? '#4ade80' : '#60a5fa',
                    }}>
                      {f.key}
                    </span>
                    <span style={{ fontSize: 9, color: 'var(--border-strong)' }}>{f.type}</span>
                    {f.required && (
                      <span style={{ fontSize: 9, color: 'var(--danger-dim)', fontWeight: 700 }}>req</span>
                    )}
                    {copiedId === fieldId && (
                      <span style={{ fontSize: 9, color: '#4ade80' }}>✓ copiado</span>
                    )}
                  </div>
                  {(f.hint || f.label) && (
                    <span style={{ fontSize: 10, color: 'var(--text-subtle)', paddingLeft: 10 }}>
                      {f.hint || f.label}
                    </span>
                  )}
                  {Array.isArray(f.options) && f.options.length > 0 && (
                    <div style={{
                      marginLeft: 10,
                      maxHeight: 130,
                      overflowY: 'auto',
                      display: 'flex',
                      flexDirection: 'column',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                    }}>
                      {f.options.map(opt => {
                        const optId = `opt:${f.key}:${opt.value}`
                        return (
                          <div
                            key={optId}
                            onClick={() => copyToClipboard(opt.value, optId)}
                            title="Clic para copiar el valor"
                            style={{
                              fontSize: 10,
                              padding: '3px 6px',
                              cursor: 'pointer',
                              color: copiedId === optId ? '#4ade80' : 'var(--text-subtle)',
                              background: copiedId === optId ? 'var(--success-dim)' : 'transparent',
                              borderBottom: '1px solid var(--border)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              gap: 8,
                            }}
                          >
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {opt.label || opt.value}
                            </span>
                            {copiedId === optId && <span style={{ flexShrink: 0 }}>✓</span>}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
