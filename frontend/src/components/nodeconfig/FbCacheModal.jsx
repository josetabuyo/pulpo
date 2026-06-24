import { useState, useEffect } from 'react'

function relTime(ts) {
  const diff = Math.floor((Date.now() / 1000) - ts)
  if (diff < 60)  return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}min`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`
  return `${Math.floor(diff / 86400)}d`
}

function shortUrl(url) {
  return url.replace('https://www.facebook.com/', 'fb/')
}

export default function FbCacheModal({ pageId, apiCall, onClose }) {
  const [posts, setPosts] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiCall('GET', `/fb/cache?page_id=${pageId}`, null)
      .then(r => {
        if (r?.posts) setPosts(r.posts)
        else setError('No se pudo cargar la cache')
      })
      .catch(() => setError('Error de red'))
  }, [pageId])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#0f172a', border: '1px solid #1e293b',
          borderRadius: 12, padding: 20, width: 760, maxWidth: '95vw',
          maxHeight: '85vh', display: 'flex', flexDirection: 'column',
          boxShadow: '0 16px 48px rgba(0,0,0,.6)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <span style={{ color: '#e2e8f0', fontWeight: 700, fontSize: 14 }}>Cache FB</span>
            <span style={{ color: '#475569', fontSize: 12, marginLeft: 8 }}>{pageId}</span>
            {posts && (
              <span style={{
                marginLeft: 8, background: '#1e293b', color: '#94a3b8',
                borderRadius: 10, padding: '1px 8px', fontSize: 11,
              }}>{posts.length}</span>
            )}
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
          >×</button>
        </div>

        {/* Content */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {!posts && !error && (
            <div style={{ color: '#475569', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>Cargando…</div>
          )}
          {error && (
            <div style={{ color: '#f87171', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>{error}</div>
          )}
          {posts && posts.length === 0 && (
            <div style={{ color: '#475569', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>Cache vacía</div>
          )}
          {posts && posts.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1e293b' }}>
                  {['URL', 'Texto', 'Queries', 'Visto'].map(h => (
                    <th key={h} style={{ color: '#475569', fontWeight: 600, padding: '4px 8px', textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {posts.map((p, i) => (
                  <tr key={p.url} style={{ borderBottom: '1px solid #0f172a', background: i % 2 === 0 ? '#0f172a' : '#111827' }}>
                    <td style={{ padding: '6px 8px', maxWidth: 180 }}>
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: '#60a5fa', textDecoration: 'none', wordBreak: 'break-all', fontSize: 10 }}
                        title={p.url}
                      >
                        {shortUrl(p.url).slice(0, 40)}{p.url.length > 40 ? '…' : ''}
                      </a>
                    </td>
                    <td style={{ padding: '6px 8px', color: '#94a3b8', maxWidth: 280 }}>
                      <span title={p.text}>
                        {p.text ? p.text.slice(0, 100).replace(/\n/g, ' ') + (p.text.length > 100 ? '…' : '') : <em style={{ color: '#334155' }}>sin texto</em>}
                      </span>
                    </td>
                    <td style={{ padding: '6px 8px', maxWidth: 120 }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                        {(p.queries || []).map(q => (
                          <span key={q} style={{
                            background: '#1e293b', color: '#7dd3fc',
                            borderRadius: 4, padding: '1px 5px', fontSize: 10, whiteSpace: 'nowrap',
                          }}>{q}</span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '6px 8px', color: '#475569', whiteSpace: 'nowrap' }}>
                      {relTime(p.last_seen)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
