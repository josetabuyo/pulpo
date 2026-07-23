import { useEffect, useState } from 'react'

const CELLS = 4 // mosaico 2x2

// Default de PulpoChat cuando el bot no configuró banners propios --
// simple, sin depender de ningún asset externo.
const DEFAULT_BANNERS = [
  { html: "<div style='display:flex;align-items:center;justify-content:center;height:100%;font-size:28px'>🐙</div>" },
]

function BannerCell({ banner }) {
  if (!banner) return <div className="pc-banner-cell" />
  if (banner.img) {
    const img = <img src={banner.img} alt={banner.alt || ''} />
    return (
      <div className="pc-banner-cell">
        {banner.href ? <a href={banner.href} target="_blank" rel="noopener noreferrer">{img}</a> : img}
      </div>
    )
  }
  if (banner.html) {
    // HTML estático del cliente -- sandboxed sin scripts ni top-navigation
    // (§5.4 del handoff: un PRO no debe poder inyectar JS que corra con la
    // sesión de OTRO usuario del chat, p.ej. un admin que abre ese chat).
    return (
      <div className="pc-banner-cell">
        <iframe srcDoc={banner.html} sandbox="" title="banner" />
      </div>
    )
  }
  return <div className="pc-banner-cell" />
}

/**
 * Zona arriba a la derecha, mosaico de cuadrados intercambiables. Rotación
 * simple con setInterval si hay más banners que celdas (fade).
 */
export default function ChatBanners({ banners, open }) {
  const list = banners && banners.length > 0 ? banners : DEFAULT_BANNERS
  const [offset, setOffset] = useState(0)
  const [fading, setFading] = useState(false)

  useEffect(() => {
    if (list.length <= CELLS) return
    const id = setInterval(() => {
      setFading(true)
      setTimeout(() => {
        setOffset(o => (o + CELLS) % list.length)
        setFading(false)
      }, 400)
    }, 6000)
    return () => clearInterval(id)
  }, [list.length])

  const visible = Array.from({ length: CELLS }, (_, i) => list[(offset + i) % list.length])

  return (
    <div className={`pc-banners ${open ? 'pc-banners--open' : ''}`}>
      <div className="pc-banners-title">PulpoChat</div>
      <div className="pc-banner-grid" style={{ opacity: fading ? 0 : 1, transition: 'opacity .4s ease' }}>
        {visible.map((banner, i) => <BannerCell key={i} banner={banner} />)}
      </div>
    </div>
  )
}
