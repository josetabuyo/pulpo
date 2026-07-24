import { useState } from 'react'

/**
 * Textarea + Enter para enviar, deshabilitado mientras corre el run
 * (§3 del handoff: run_status === 'running').
 */
export default function ChatComposer({ disabled, onSend }) {
  const [value, setValue] = useState('')

  function submit() {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="pc-composer">
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Esperando respuesta...' : 'Escribí un mensaje...'}
        disabled={disabled}
        rows={1}
      />
      <button className="pc-send-btn" onClick={submit} disabled={disabled || !value.trim()}>
        Enviar
      </button>
    </div>
  )
}
