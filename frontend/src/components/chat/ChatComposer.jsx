import { useRef, useState } from 'react'

/**
 * Textarea + Enter para enviar, deshabilitado mientras corre el run
 * (§3 del handoff: run_status === 'running'). `onSend(text, file)` -- el
 * padre (PulpoChatWidget) hace el upload del file antes de mandar el
 * mensaje, esto solo junta texto + archivo elegido.
 */
export default function ChatComposer({ disabled, onSend }) {
  const [value, setValue] = useState('')
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const fileInputRef = useRef(null)

  function submit() {
    const text = value.trim()
    if (!text && !file) return
    if (disabled) return
    onSend(text, file)
    setValue('')
    clearFile()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function handleFileChange(e) {
    const picked = e.target.files?.[0]
    if (!picked) return
    setFile(picked)
    setPreviewUrl(URL.createObjectURL(picked))
  }

  function clearFile() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setFile(null)
    setPreviewUrl('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="pc-composer-wrap">
      {previewUrl && (
        <div className="pc-composer-preview">
          <img src={previewUrl} alt="adjunto elegido" />
          <button type="button" onClick={clearFile} aria-label="Quitar adjunto">✕</button>
        </div>
      )}
      <div className="pc-composer">
        <button
          type="button"
          className="pc-attach-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          aria-label="Adjuntar imagen"
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          hidden
        />
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Esperando respuesta...' : 'Escribí un mensaje...'}
          disabled={disabled}
          rows={1}
        />
        <button
          className="pc-send-btn"
          onClick={submit}
          disabled={disabled || (!value.trim() && !file)}
          aria-label="Enviar"
          title="Enviar"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
            <path d="M3.4 20.4l17.45-7.48a1 1 0 0 0 0-1.84L3.4 3.6a1 1 0 0 0-1.4 1.03l1.55 6.63a1 1 0 0 0 .78.76l8.27 1.98-8.27 1.98a1 1 0 0 0-.78.76L2 19.37a1 1 0 0 0 1.4 1.03z" />
          </svg>
        </button>
      </div>
    </div>
  )
}
