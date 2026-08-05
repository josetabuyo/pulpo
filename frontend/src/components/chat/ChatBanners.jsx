import { useEffect, useState } from 'react'

const CELLS = 4 // mosaico Mondrian: 1 grande + 3 chicas

// Default "de fábrica" de PulpoChat: un bot que todavía no cargó su propia
// publicidad no debe mostrar un rail vacío -- muestra esto, que además
// promociona Pulpo. El cliente pisa este set en cuanto publica su primera
// publicidad propia (ver ChatBanners() más abajo: `usingAds`/`banners.length`
// gana siempre que haya algo real cargado).
const PULPO_REPO_URL = 'https://github.com/josetabuyo/pulpo'
const DEFAULT_BANNERS = [
  {
    img: 'https://images.unsplash.com/photo-1561479639-747efc0d0bf2?fm=jpg&q=80&w=800&auto=format&fit=crop',
    href: PULPO_REPO_URL,
    alt: 'Pulpo',
    title: 'Hecho con Pulpo',
  },
  {
    img: '/pulpo.svg',
    href: PULPO_REPO_URL,
    alt: 'Pulpo',
    title: 'github.com/josetabuyo/pulpo',
  },
  {
    img: 'https://images.unsplash.com/photo-1558729924-714b0a8e0574?fm=jpg&q=80&w=800&auto=format&fit=crop',
    href: PULPO_REPO_URL,
    alt: 'Pulpo',
  },
  {
    img: 'https://images.unsplash.com/photo-1548645933-c62d4468cbb9?fm=jpg&q=80&w=800&auto=format&fit=crop',
    href: PULPO_REPO_URL,
    alt: 'Pulpo',
    title: 'Armá tu propio chat con Pulpo',
  },
]

function AdCell({ item }) {
  if (!item) return <div className="pc-ad-cell" />
  // Forma "ad" (chat_ads, ver lib/business/chat-ads.ts) o legacy banner
  // ({img,href,alt} | {html}) -- normalizamos acá para que el resto del
  // componente no le importe de dónde vino.
  const img = item.image_url || item.img
  const href = item.link_url || item.href
  const title = item.title

  if (img) {
    const el = (
      <>
        <img src={img} alt={item.alt || title || ''} />
        {title && <span className="pc-ad-title">{title}</span>}
      </>
    )
    return (
      <div className="pc-ad-cell">
        {href ? <a href={href} target="_blank" rel="noopener noreferrer">{el}</a> : el}
      </div>
    )
  }
  if (item.html) {
    // HTML estático del cliente -- sandboxed sin scripts ni top-navigation
    // (un PRO no debe poder inyectar JS que corra con la sesión de OTRO
    // usuario del chat, p.ej. un admin que abre ese chat).
    return (
      <div className="pc-ad-cell">
        <iframe srcDoc={item.html} sandbox="" title="publicidad" />
      </div>
    )
  }
  return <div className="pc-ad-cell" />
}

/**
 * Rail derecho, full-height, mosaico tipo Mondrian de hasta 4 publicidades
 * (`ads`, la cola FILO de lib/business/chat-ads.ts -- ya viene recortada a
 * 4 y sin necesidad de rotar). Si el chat no tiene ninguna fila en
 * chat_ads todavía, cae al `banners` legacy (JSON manual de chat_configs) y
 * mantiene la rotación vieja si hay más de 4 -- así un chat configurado
 * antes de esta feature sigue funcionando sin migrar datos.
 */
export default function ChatBanners({ ads, banners, open }) {
  const usingAds = Array.isArray(ads) && ads.length > 0
  const list = usingAds ? ads : (banners && banners.length > 0 ? banners : DEFAULT_BANNERS)
  const rotates = !usingAds && list.length > CELLS

  const [offset, setOffset] = useState(0)
  const [fading, setFading] = useState(false)

  useEffect(() => {
    if (!rotates) return
    const id = setInterval(() => {
      setFading(true)
      setTimeout(() => {
        setOffset(o => (o + CELLS) % list.length)
        setFading(false)
      }, 400)
    }, 6000)
    return () => clearInterval(id)
  }, [rotates, list.length])

  const visible = Array.from({ length: CELLS }, (_, i) => list[(offset + i) % list.length])

  return (
    <div className={`pc-ads ${open ? 'pc-ads--open' : ''}`}>
      <div className="pc-ads-title">Publicidad</div>
      <div className="pc-ad-grid" style={{ opacity: fading ? 0 : 1, transition: 'opacity .4s ease' }}>
        {visible.map((item, i) => <AdCell key={item?.id ?? i} item={item} />)}
      </div>
    </div>
  )
}
