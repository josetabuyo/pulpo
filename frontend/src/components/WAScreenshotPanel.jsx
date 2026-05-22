import { useState, useEffect, useRef, useCallback } from 'react'

// zoomFactor: cuántas veces más grande es el viewport vs el panel.
// 2 = viewport 2× panel → WA aparece al 50% → el default que se ve bien.
// Más alto = más zoom out (más contenido WA visible, más pequeño).
const ZOOM_STEPS = [1, 1.5, 2, 3, 4]

export default function WAScreenshotPanel({ empresaId, apiCall, active }) {
  const [src, setSrc] = useState(null)
  const [zoomFactor, setZoomFactor] = useState(2)
  const intervalRef = useRef(null)
  const panelRef   = useRef(null)
  const imgWrapRef = useRef(null)
  const dragRef    = useRef({ dragging: false })

  // Ancho del panel × factor; alto del IMG WRAP × factor (excluye la barra de controles).
  function sendResize(factor) {
    const panel   = panelRef.current
    const imgWrap = imgWrapRef.current
    if (!panel || !imgWrap) return
    const w = Math.round(panel.offsetWidth   * factor)
    const h = Math.round(imgWrap.offsetHeight * factor)
    if (w < 280 || h < 200) return
    apiCall('POST', `/summarizer/${empresaId}/wa-resize`, { width: w, height: h }).catch(() => {})
  }

  function fetchScreenshot() {
    return apiCall('GET', `/summarizer/${empresaId}/wa-screenshot`, null)
      .then(data => { if (data?.screenshot) setSrc(data.screenshot) })
      .catch(() => {})
  }

  // Al activar: viewport = 2× panel (default zoom)
  useEffect(() => {
    if (!active) return
    const t = setTimeout(() => sendResize(zoomFactor), 150)
    return () => clearTimeout(t)
  }, [active, empresaId])

  // Polling de screenshot
  useEffect(() => {
    if (!active) {
      clearInterval(intervalRef.current)
      return
    }
    fetchScreenshot()
    intervalRef.current = setInterval(fetchScreenshot, 3000)
    return () => clearInterval(intervalRef.current)
  }, [active, empresaId])

  function scrollWA(direction) {
    apiCall('POST', `/summarizer/${empresaId}/wa-scroll`, { direction, amount: 300 }).catch(() => {})
  }

  function changeZoom(delta) {
    const idx = ZOOM_STEPS.indexOf(zoomFactor)
    const nextIdx = Math.max(0, Math.min(ZOOM_STEPS.length - 1, idx + delta))
    const next = ZOOM_STEPS[nextIdx]
    if (next === zoomFactor) return
    setZoomFactor(next)
    sendResize(next)
  }

  // Drag-resize handle
  const onResizeMouseDown = useCallback((e) => {
    e.preventDefault()
    const panel = panelRef.current
    if (!panel) return
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      startW: panel.offsetWidth,
      startH: panel.offsetHeight,
    }

    function onMouseMove(e) {
      if (!dragRef.current.dragging) return
      const { startX, startY, startW, startH } = dragRef.current
      const newW = Math.max(280, startW + (e.clientX - startX))
      const newH = Math.max(200, startH + (e.clientY - startY))
      if (panelRef.current) {
        panelRef.current.style.width  = newW + 'px'
        panelRef.current.style.height = newH + 'px'
        panelRef.current.style.flex   = 'none'
      }
    }

    function onMouseUp() {
      if (!dragRef.current.dragging) return
      dragRef.current.dragging = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup',   onMouseUp)
      sendResize(zoomFactor)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup',   onMouseUp)
  }, [empresaId, apiCall, zoomFactor])

  const zoomPct = Math.round(100 / zoomFactor) + '%'

  return (
    <div className="wa-screenshot-panel" ref={panelRef}>
      <div className="wa-screenshot-controls">
        <button className="wa-scroll-btn" onClick={() => scrollWA('up')} title="Scroll WA arriba">▲</button>
        <div className="wa-zoom-controls">
          <button className="wa-scroll-btn" onClick={() => scrollWA('left')}  title="Pan WA izquierda">◄</button>
          <button className="wa-scroll-btn" onClick={() => changeZoom(1)}     title="Zoom out"
            disabled={zoomFactor >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}>−</button>
          <span className="wa-zoom-label">{zoomPct}</span>
          <button className="wa-scroll-btn" onClick={() => changeZoom(-1)}    title="Zoom in"
            disabled={zoomFactor <= ZOOM_STEPS[0]}>+</button>
          <button className="wa-scroll-btn" onClick={() => scrollWA('right')} title="Pan WA derecha">►</button>
        </div>
        <div style={{display:'flex', gap:'2px'}}>
          <button className="wa-scroll-btn" onClick={() => scrollWA('down')}   title="Scroll WA abajo">▼</button>
          <button className="wa-scroll-btn" onClick={() => scrollWA('bottom')} title="Ir al último mensaje">⏬</button>
        </div>
      </div>
      <div className="wa-screenshot-img-wrap" ref={imgWrapRef}>
        {src
          ? <img src={src} alt="WA Web" className="wa-screenshot-img" />
          : <div className="wa-screenshot-placeholder">{active ? 'Cargando…' : '—'}</div>
        }
      </div>
      <div className="wa-resize-handle" onMouseDown={onResizeMouseDown} title="Arrastrar para redimensionar" />
    </div>
  )
}
