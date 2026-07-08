/**
 * MermaidDiagram — renderiza un diagrama mermaid (texto plano) como SVG inline.
 * Client-side, sin CDN: mermaid.js vive en node_modules como cualquier otra dependencia.
 */
import { useEffect, useRef, useState } from 'react'

let _mermaidPromise = null
function loadMermaid() {
  if (!_mermaidPromise) {
    _mermaidPromise = import('mermaid').then(m => {
      const mermaid = m.default
      mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })
      return mermaid
    })
  }
  return _mermaidPromise
}

let _diagramCounter = 0

export default function MermaidDiagram({ source, title }) {
  const [svg, setSvg] = useState(null)
  const [error, setError] = useState(null)
  const idRef = useRef(`mermaid-${++_diagramCounter}`)

  useEffect(() => {
    let cancelled = false
    loadMermaid()
      .then(mermaid => mermaid.render(idRef.current, source))
      .then(({ svg }) => { if (!cancelled) setSvg(svg) })
      .catch(err => { if (!cancelled) setError(err.message || String(err)) })
    return () => { cancelled = true }
  }, [source])

  return (
    <div className="arch-diagram">
      {title && <h4>{title}</h4>}
      {error && <div className="arch-test-empty">Error renderizando diagrama: {error}</div>}
      {!error && !svg && <div className="arch-test-empty">Renderizando…</div>}
      {svg && <div className="arch-diagram-svg" dangerouslySetInnerHTML={{ __html: svg }} />}
    </div>
  )
}
