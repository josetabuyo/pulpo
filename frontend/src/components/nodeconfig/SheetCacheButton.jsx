/**
 * Botón para limpiar el caché de hojas (nodos fetch_sheet / search_sheet / gsheet).
 */
import { useState } from 'react'

export default function SheetCacheButton({ apiCall }) {
  const [status, setStatus] = useState('')
  async function handleClear() {
    setStatus('Limpiando...')
    try {
      const res = await apiCall('POST', '/flow/clear-sheet-cache', null)
      setStatus(`✓ Caché limpiado (${res.cleared} entradas)`)
    } catch {
      setStatus('Error al limpiar')
    }
    setTimeout(() => setStatus(''), 3000)
  }
  return (
    <div style={{ paddingTop: 8, borderTop: '1px solid #1e293b' }}>
      <button
        onClick={handleClear}
        style={{
          width: '100%', padding: '7px 12px',
          background: 'transparent', border: '1px solid #0e7490',
          borderRadius: 6, color: '#22d3ee', fontSize: 12,
          cursor: 'pointer', fontWeight: 600,
        }}
      >
        🗑 Limpiar caché de hoja
      </button>
      {status && <div style={{ fontSize: 11, color: '#22d3ee', textAlign: 'center', marginTop: 4 }}>{status}</div>}
    </div>
  )
}
