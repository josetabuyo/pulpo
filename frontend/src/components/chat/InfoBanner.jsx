import { useEffect, useState } from 'react'

// Franja tipo noticiero pegada debajo del header (pc-header) -- hora +
// fecha + temperatura de la ubicación de QUIEN ESTÁ USANDO EL CHAT ahora
// mismo, detectada por IP vía /api/geo (ver ese route: ipwho.is, sin pedir
// permiso al visitante). No es una ubicación fija por chat/cliente -- cada
// visitante ve la suya propia. Si la detección falla (ver useGeoLocation),
// cae a infoBanner.location (config del admin, ver lib/business/
// chats.ts::DEFAULT_BANNER_LOCATION) como fallback, y si tampoco hay eso,
// no se muestra fecha/hora/temp (solo el mensaje del ticker). El mensaje en
// sí sigue siendo editable (chat_configs.info_banner.message, actualizable
// por el cliente vía POST /api/chat/{botId}/{chatId}/info-banner con
// X-Pulpo-Bot-Key). Si info_banner.enabled es false, no renderiza nada.

function useGeoLocation(fallback) {
  const [location, setLocation] = useState(fallback)
  useEffect(() => {
    let cancelled = false
    fetch('/api/geo').then(r => r.json()).then(d => {
      if (cancelled) return
      if (typeof d?.lat === 'number' && typeof d?.lon === 'number' && d?.timezone) {
        setLocation(d)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])
  return location
}

function useClock(timezone) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])
  const clockFmt = new Intl.DateTimeFormat('es-AR', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })
  const dateFmt = new Intl.DateTimeFormat('es-AR', { timeZone: timezone, day: '2-digit', month: 'short' })
  return { time: clockFmt.format(now), date: dateFmt.format(now).replace('.', '') }
}

function useTemp(lat, lon) {
  const [temp, setTemp] = useState(null)
  useEffect(() => {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    let cancelled = false
    fetch(`/api/weather?lat=${lat}&lon=${lon}`).then(r => r.json()).then(d => {
      if (!cancelled && typeof d?.temperature_c === 'number') setTemp(d.temperature_c)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [lat, lon])
  return temp
}

export default function InfoBanner({ infoBanner }) {
  const location = useGeoLocation(infoBanner?.location || {})
  const { time, date } = useClock(location.timezone || 'UTC')
  const temp = useTemp(location.lat, location.lon)

  if (!infoBanner?.enabled || !infoBanner?.message) return null

  return (
    <div className="pc-infobanner" role="status">
      <span className="pc-infobanner-live">
        <span className="pc-infobanner-dot" />
        <span className="pc-infobanner-live-label">{location.label || 'En vivo'}</span>
      </span>
      <span className="pc-infobanner-stat">📅 {date}</span>
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
