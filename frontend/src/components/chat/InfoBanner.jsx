import { useEffect, useState } from 'react'

// Franja tipo noticiero pegada debajo del header (pc-header) -- hora +
// temperatura de Lugano (calculadas/fetcheadas acá, no viven en DB) + un
// mensaje editable (chat_configs.info_banner, actualizable por Luganense
// vía POST /api/chat/{botId}/{chatId}/info-banner con X-Pulpo-Bot-Key). Si
// info_banner.enabled es false, el componente no renderiza nada.

const LUGANO_TZ = 'Europe/Zurich'
const CLOCK_FMT = new Intl.DateTimeFormat('es-AR', { timeZone: LUGANO_TZ, hour: '2-digit', minute: '2-digit' })

function useLuganoClock() {
  const [time, setTime] = useState(() => CLOCK_FMT.format(new Date()))
  useEffect(() => {
    const id = setInterval(() => setTime(CLOCK_FMT.format(new Date())), 30_000)
    return () => clearInterval(id)
  }, [])
  return time
}

function useLuganoTemp() {
  const [temp, setTemp] = useState(null)
  useEffect(() => {
    let cancelled = false
    fetch('/api/weather/lugano').then(r => r.json()).then(d => {
      if (!cancelled && typeof d?.temperature_c === 'number') setTemp(d.temperature_c)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])
  return temp
}

export default function InfoBanner({ infoBanner }) {
  const time = useLuganoClock()
  const temp = useLuganoTemp()

  if (!infoBanner?.enabled || !infoBanner?.message) return null

  return (
    <div className="pc-infobanner" role="status">
      <span className="pc-infobanner-live">
        <span className="pc-infobanner-dot" />
        Lugano
      </span>
      <span className="pc-infobanner-stat">🕒 {time}</span>
      {temp !== null && <span className="pc-infobanner-stat">🌡️ {Math.round(temp)}°C</span>}
      <div className="pc-infobanner-ticker">
        <div className="pc-infobanner-ticker-track">
          <span>{infoBanner.message}</span>
          <span aria-hidden="true">{infoBanner.message}</span>
        </div>
      </div>
    </div>
  )
}
