/**
 * ArchitectureSection — radiografía viva del sistema, dentro del dashboard.
 *
 * Consume GET /api/architecture: descripción del sistema, catálogo dinámico
 * de nodos del motor de flows, rutas reales de la API, canales activos y los
 * últimos reportes de tests (pytest + Playwright) generados por las suites.
 *
 * Deep link: /dashboard?arquitectura=1 (alias: /dashboard/arquitectura).
 * Visual: panel oscuro autocontenido inspirado en boarding.html de wavi.
 */
import { useState, useEffect, useRef } from 'react'
import { apiQuiet } from '../api.js'
import MermaidDiagram from './MermaidDiagram.jsx'
import { LAYERS_DIAGRAM, CONNECTIONS_DIAGRAM } from '../architectureDiagrams.js'
import './architecture.css'

const SECTIONS = [
  ['vision', 'Visión'],
  ['diagramas', 'Diagramas'],
  ['stack', 'Stack'],
  ['flows', 'Motor de flows'],
  ['api', 'API'],
  ['canales', 'Canales'],
  ['tests', 'Tests'],
]

function fmtTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return isNaN(d) ? ts : d.toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const OUTCOME_DOT = { passed: '🟢', failed: '🔴', error: '🔴', skipped: '⚪' }

function TestPanel({ title, cmd, report }) {
  if (!report) {
    return (
      <div className="arch-test-panel">
        <h4>{title}</h4>
        <div className="arch-test-empty">
          Sin reporte todavía — corré <code>{cmd}</code> para generarlo.
        </div>
      </div>
    )
  }
  return (
    <div className="arch-test-panel">
      <h4>{title}</h4>
      <div className="arch-test-meta">
        {fmtTs(report.timestamp)} · {report.duration}s · {report.total} tests
      </div>
      <div className="arch-test-counts">
        <div className="arch-test-count">
          <div className="arch-num arch-num--pass">{report.passed}</div>
          <div className="arch-cap">passed</div>
        </div>
        <div className="arch-test-count">
          <div className="arch-num arch-num--fail">{report.failed}</div>
          <div className="arch-cap">failed</div>
        </div>
        <div className="arch-test-count">
          <div className="arch-num arch-num--skip">{report.skipped}</div>
          <div className="arch-cap">skipped</div>
        </div>
      </div>
      <div className="arch-test-list">
        {(report.tests || []).map((t, i) => (
          <div className="arch-test-row" key={i}>
            <span className="arch-tdot">{OUTCOME_DOT[t.outcome] || '⚪'}</span>
            <span className="arch-tname" title={t.nodeid}>{t.nodeid}</span>
            <span className="arch-tdur">{t.duration}s</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ArchitectureSection({ collapsed }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef(null)

  async function load() {
    setLoading(true)
    setError(false)
    const d = await apiQuiet('GET', '/architecture', null, 'architecture')
    if (d && d.system) setData(d)
    else setError(true)
    setLoading(false)
  }

  // Fetch lazy: recién al expandir la sección por primera vez
  useEffect(() => {
    if (!collapsed && !data && !loading) load()
  }, [collapsed])

  function scrollTo(id) {
    panelRef.current?.querySelector(`#arch-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (collapsed) return null
  if (loading && !data) return <div className="arch-panel"><div className="arch-loading">Cargando arquitectura…</div></div>
  if (error && !data) return (
    <div className="arch-panel">
      <div className="arch-error">
        No se pudo cargar /api/architecture.{' '}
        <button className="btn-ghost btn-sm" onClick={load}>Reintentar</button>
      </div>
    </div>
  )
  if (!data) return null

  const { system, flow_engine, api: apiInfo, channels, tests } = data

  return (
    <div className="arch-panel" ref={panelRef}>
      <div className="arch-nav">
        {SECTIONS.map(([id, label]) => (
          <button key={id} onClick={() => scrollTo(id)}>{label}</button>
        ))}
        <button className="arch-nav-refresh" onClick={load} title="Recargar datos">↺ Actualizar</button>
      </div>

      {/* ── Visión general ── */}
      <div className="arch-hero" id="arch-vision">
        <h2>🐙 Pulpo <span className="arch-accent">— arquitectura</span></h2>
        <p>{system.description}</p>
        <div className="arch-badges">
          <span className="arch-badge">commit <b>{system.version_commit}</b></span>
          <span className="arch-badge">FastAPI <b>:8000</b></span>
          <span className="arch-badge">React + Vite <b>:5173</b></span>
          <span className="arch-badge">SQLite</span>
          <span className="arch-badge"><b>{channels.bots_active}</b>/{channels.bots_total} bots activos</span>
          <span className="arch-badge"><b>{channels.telegram_bots}</b> bots TG</span>
          <span className="arch-badge"><b>{channels.wavi_sessions}</b> sesiones wavi</span>
          <span className="arch-badge"><b>{apiInfo.total_routes}</b> rutas API</span>
        </div>
      </div>

      {/* ── Diagramas ── */}
      <div className="arch-section" id="arch-diagramas">
        <h3><span className="arch-hash">#</span>Diagramas</h3>
        <p className="arch-diagram-note">
          Mantenidos a mano — revisar cuando se mueven o renombran módulos (ver CLAUDE.md).
        </p>
        <MermaidDiagram source={LAYERS_DIAGRAM} title="Capas — quién puede importar a quién" />
        <MermaidDiagram source={CONNECTIONS_DIAGRAM} title="Conexiones — canales, drivers y dónde persiste cada uno" />
      </div>

      {/* ── Stack y módulos ── */}
      <div className="arch-section" id="arch-stack">
        <h3><span className="arch-hash">#</span>Stack y módulos</h3>
        <div className="arch-cards">
          <div className="arch-card">
            <h4>Backend — FastAPI</h4>
            <p>Lifespan levanta bots de Telegram y el poller wavi. {apiInfo.total_routes} rutas
              bajo /api. El motor de flows (graphs/) ejecuta BFS desde el trigger que aplica.</p>
          </div>
          <div className="arch-card">
            <h4>Motor de flows</h4>
            <p>compiler.py orquesta; trigger_match.py decide qué trigger aplica (canal,
              conexión, contactos, regex); cooldown.py limita la frecuencia de replies.</p>
          </div>
          <div className="arch-card">
            <h4>Frontend — React + Vite</h4>
            <p>Dashboard admin con secciones colapsables sincronizadas a la URL, editor
              visual de flows (React Flow) y portal de bot con JWT.</p>
          </div>
          <div className="arch-card">
            <h4>Datos</h4>
            <p>SQLite (data/messages.db): mensajes, contactos, flows, sesiones, dedup wavi.
              Resúmenes por contacto en data/summaries/ (markdown + adjuntos).</p>
          </div>
        </div>
        <div className="arch-callout">
          <b>contact_phone no siempre es un teléfono.</b> Es el ID del contacto en su canal:{' '}
          <code>telegram → {system.contact_phone_semantics.telegram}</code> ·{' '}
          <code>wavi → display name</code> ·{' '}
          <code>sim → teléfono</code>. Filtros, cooldowns y resúmenes se indexan por este valor.
        </div>
      </div>

      {/* ── Motor de flows ── */}
      <div className="arch-section" id="arch-flows">
        <h3><span className="arch-hash">#</span>Motor de flows — {flow_engine.nodes.length} tipos de nodo</h3>
        <div className="arch-nodes">
          {flow_engine.nodes.map(n => (
            <div className="arch-node" key={n.id}>
              <div className="arch-node-head">
                <span className="arch-node-dot" style={{ background: n.color }} />
                <span className="arch-node-label">{n.label}</span>
                {n.is_trigger && <span className="arch-node-trigger">TRIGGER</span>}
              </div>
              <p className="arch-node-desc">{n.description}</p>
              {n.config_keys.length > 0 && (
                <div className="arch-node-keys">
                  {n.config_keys.map(k => <span key={k}>{k}</span>)}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── API ── */}
      <div className="arch-section" id="arch-api">
        <h3><span className="arch-hash">#</span>API — {apiInfo.total_routes} rutas</h3>
        <div className="arch-routes">
          <table>
            <thead>
              <tr><th>Métodos</th><th>Ruta</th></tr>
            </thead>
            <tbody>
              {apiInfo.routes.map((r, i) => (
                <tr key={i}>
                  <td>
                    {r.methods.map(m => (
                      <span key={m} className={`arch-method arch-method--${m}`}>{m}</span>
                    ))}
                  </td>
                  <td className="arch-route-path">{r.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Canales ── */}
      <div className="arch-section" id="arch-canales">
        <h3><span className="arch-hash">#</span>Canales</h3>
        <div className="arch-cards">
          <div className="arch-card">
            <h4>Telegram — {channels.telegram_bots} bots</h4>
            <p>python-telegram-bot en modo polling, levantado en el lifespan.
              Cada conexión vive en connections.json y dispara telegram_trigger.</p>
          </div>
          <div className="arch-card">
            <h4>WhatsApp (wavi) — {channels.wavi_sessions} sesiones</h4>
            <p>Poller cada {Math.round(channels.wa_poll_interval_seconds / 60)} min sobre el CLI wavi
              (vision pipeline). Dedup persistente en SQLite — sobrevive reinicios.</p>
          </div>
          <div className="arch-card">
            <h4>Simulador</h4>
            <p>En worktrees dev (ENABLE_BOTS=false) los canales se simulan: el pipeline
              completo corre sin browsers ni conexiones reales.</p>
          </div>
        </div>
      </div>

      {/* ── Tests vivos ── */}
      <div className="arch-section" id="arch-tests">
        <h3><span className="arch-hash">#</span>Tests — resultados reales de la última corrida</h3>
        <div className="arch-tests">
          <TestPanel title="Backend — pytest (unit + integración)" cmd="uv run pytest pulpo/ tests/ -v" report={tests.backend} />
          <TestPanel title="Frontend — Playwright" cmd="cd frontend && npx playwright test" report={tests.frontend} />
        </div>
      </div>
    </div>
  )
}
