/**
 * Botón para limpiar el caché de hojas (nodos fetch_sheet / search_sheet / gsheet).
 */
import { useState } from 'react'

export default function SheetCacheButton({ apiCall }) {
  const [status, setStatus] = useState('')
  async function handleClear() {
    setStatus('Limpiando...')
    try {
      const res = await apiCall('POST', '/flows/clear-sheet-cache', null)
      setStatus(`✓ Caché limpiado (${res.cleared} entradas)`)
    } catch {
      setStatus('Error al limpiar')
    }
    setTimeout(() => setStatus(''), 3000)
  }
  return (
    <div style={{ paddingTop: 8, borderTop: '1px solid var(--surface-2)' }}>
      <button
        onClick={handleClear}
        style={{
          width: '100%', padding: '7px 12px',
          background: 'transparent', border: '1px solid var(--tg)',
          borderRadius: 6, color: 'var(--tg)', fontSize: 12,
          cursor: 'pointer', fontWeight: 600,
        }}
      >
        🗑 Limpiar caché de hoja
      </button>
      {status && <div style={{ fontSize: 11, color: 'var(--tg)', textAlign: 'center', marginTop: 4 }}>{status}</div>}
    </div>
  )
}
