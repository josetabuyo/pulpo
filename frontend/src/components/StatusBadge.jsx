export default function StatusBadge({ status }) {
  const map = {
    ready:         { cls: 's-ready',        label: 'Conectado' },
    connecting:    { cls: 's-connecting',   label: 'Conectando' },
    qr_ready:      { cls: 's-qr_needed',    label: 'Sin iniciar' },
    qr_needed:     { cls: 's-qr_needed',    label: 'Sin iniciar' },
    authenticated: { cls: 's-authenticated',label: 'Autenticando' },
    disconnected:  { cls: 's-disconnected', label: 'Desconectado' },
    failed:        { cls: 's-failed',       label: 'Error' },
    stopped:       { cls: 's-disconnected', label: 'Sin iniciar' },
  }
  const { cls, label } = map[status] ?? { cls: 's-disconnected', label: status }
  return (
    <span className={`badge ${cls}`}>
      <span className="dot" />
      {label}
    </span>
  )
}
