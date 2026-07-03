import { useState, useRef, useCallback, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { json } from '@codemirror/lang-json'
import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting, syntaxTree } from '@codemirror/language'
import { autocompletion } from '@codemirror/autocomplete'
import { tags } from '@lezer/highlight'

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
  { tag: tags.null, color: '#64748b' },
  { tag: tags.punctuation, color: '#64748b' },
  { tag: tags.brace, color: '#94a3b8' },
  { tag: tags.squareBracket, color: '#94a3b8' },
])

const pulpoTheme = EditorView.theme({
  '&': {
    backgroundColor: '#060d1a',
    color: '#e2e8f0',
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
    backgroundColor: '#050c18',
    color: '#334155',
    border: 'none',
    borderRight: '1px solid #1e293b',
  },
  '.cm-activeLineGutter': {
    backgroundColor: '#0f172a',
  },
  '.cm-activeLine': {
    backgroundColor: '#0f172a',
  },
  '.cm-foldPlaceholder': {
    backgroundColor: '#1e293b',
    color: '#64748b',
    border: 'none',
  },
  '.cm-matchingBracket': {
    backgroundColor: '#1e3a5f',
    outline: '1px solid #60a5fa',
  },
  '.cm-tooltip': {
    backgroundColor: '#0f172a',
    border: '1px solid #334155',
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
      color: '#e2e8f0',
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
    color: '#64748b',
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

export default function JsonNodeEditor({ config, schema, onChange }) {
  const stringify = c => JSON.stringify(c, null, 2)

  const [text, setText] = useState(() => stringify(config))
  const [parseError, setParseError] = useState(null)
  const lastExternal = useRef(config)
  const debounceTimer = useRef()

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

  const helpFields = (schema || []).filter(f => f.key)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

      {/* Editor */}
      <div
        style={{
          borderRadius: 6,
          border: `1px solid ${parseError ? '#7f1d1d' : '#1e293b'}`,
          overflow: 'hidden',
          transition: 'border-color 0.15s',
          resize: 'vertical',
          minHeight: 200,
          height: 200,
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
