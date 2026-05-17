import { useState, useEffect, useRef } from 'react'

export default function WAScreenshotPanel({ empresaId, apiCall, active }) {
  const [src, setSrc] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!active) {
      clearInterval(intervalRef.current)
      return
    }

    function fetchScreenshot() {
      apiCall('GET', `/summarizer/${empresaId}/wa-screenshot`, null)
        .then(data => { if (data?.screenshot) setSrc(data.screenshot) })
        .catch(() => {})
    }

    fetchScreenshot()
    intervalRef.current = setInterval(fetchScreenshot, 3000)
    return () => clearInterval(intervalRef.current)
  }, [active, empresaId])

  return (
    <div className="wa-screenshot-panel">
      {src ? (
        <img src={src} alt="WA Web screenshot" className="wa-screenshot-img" />
      ) : (
        <div className="wa-screenshot-placeholder">
          {active ? 'Sin sesión activa' : '—'}
        </div>
      )}
    </div>
  )
}
