import { useState, useEffect, useRef } from 'react'
import { api, connectAndPoll } from '../api.js'

const STEPS = { pwd: 'pwd', phone: 'phone', qr: 'qr', done: 'done' }

export default function ConnectPage() {
  const [step, setStep] = useState(STEPS.pwd)
  const [pwd, setPwd] = useState('')
  const [pwdError, setPwdError] = useState('')
  const [phone, setPhone] = useState('')
  const [phoneError, setPhoneError] = useState('')
  const [qrSrc, setQrSrc] = useState(null)
  const [qrStatus, setQrStatus] = useState('Generando código QR...')
  const stopRef = useRef(null)

  // Auto-login si hay contraseña guardada
  useEffect(() => {
    const saved = sessionStorage.getItem('client_pwd')
    if (!saved) return
    api('POST', '/auth', { password: saved })
      .then(res => {
        if (res.ok) { setPwd(saved); setStep(STEPS.phone) }
        else sessionStorage.removeItem('client_pwd')
      })
      .catch(() => {})
  }, [])

  // Cleanup al desmontar
  useEffect(() => () => { stopRef.current?.() }, [])

  async function doLogin(e) {
    e.preventDefault()
    setPwdError('')
    const res = await api('POST', '/auth', { password: pwd }).catch(() => null)
    if (!res?.ok) { setPwdError('Clave incorrecta. Verificá con el administrador.'); return }
    sessionStorage.setItem('client_pwd', pwd)
    setStep(STEPS.phone)
  }

  async function doConnect(e) {
    e.preventDefault()
    const number = phone.trim()
    if (!number) { setPhoneError('Ingresá tu número de teléfono.'); return }
    setPhoneError('')
    setStep(STEPS.qr)
    setQrSrc(null)
    setQrStatus('Generando código QR...')

    stopRef.current = await connectAndPoll({
      number,
      password: pwd,
      onQR(dataUrl) {
        setQrSrc(dataUrl)
        setQrStatus('El código se renueva cada 20 segundos')
      },
      onReady() {
        stopRef.current = null
        setStep(STEPS.done)
      },
      onError(msg) {
        setPhoneError(msg)
        setStep(STEPS.phone)
      },
    })
  }

  return (
    <div className="connect-screen">
      <div className="connect-box">
        <div className="logo">📱</div>

        {step === STEPS.pwd && (
          <>
            <h1>Conectar WhatsApp</h1>
            <p className="subtitle">Ingresá la clave de acceso que te proporcionó el administrador</p>
            <div className="error">{pwdError}</div>
            <form onSubmit={doLogin}>
              <input
                type="password"
                placeholder="Clave de acceso"
                value={pwd}
                onChange={e => setPwd(e.target.value)}
                autoFocus
              />
              <button type="submit" className="btn-connect">Continuar</button>
            </form>
          </>
        )}

        {step === STEPS.phone && (
          <>
            <h1>Tu número de WhatsApp</h1>
            <p className="subtitle">Ingresá el número que querés conectar como bot (sin el signo +)</p>
            <div className="error">{phoneError}</div>
            <form onSubmit={doConnect}>
              <input
                type="tel"
                placeholder="5491155612767"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                autoFocus
              />
              <button type="submit" className="btn-connect">Conectar</button>
            </form>
          </>
        )}

        {step === STEPS.qr && (
          <>
            <h1>Escaneá el QR</h1>
            <p className="subtitle" style={{ marginBottom: 0 }}>
              Abrí WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong>
            </p>
            <div className="qr-wrap-lg">
              {qrSrc
                ? <img src={qrSrc} alt="QR" />
                : <div className="spinner-lg" />
              }
            </div>
            <p className="subtitle">{qrStatus}</p>
          </>
        )}

        {step === STEPS.done && (
          <>
            <div className="success-icon-lg">✅</div>
            <div className="success-text-lg">¡Conectado correctamente!</div>
            <p className="success-sub">Tu WhatsApp ya está funcionando como bot. Podés cerrar esta ventana.</p>
          </>
        )}
      </div>
    </div>
  )
}
