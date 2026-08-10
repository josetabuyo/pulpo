/**
 * Vista de solo lectura para secciones con mode: "detail" (ej. noticias) --
 * ver ChatDirectory.jsx. Sin form ni lead: solo muestra los campos mapeados
 * por item_map y, si la sección lo definió (item_map.link), un botón para
 * ir a la fuente original.
 */
export default function ChatDirectoryDetail({ item, onClose }) {
  return (
    <div className="pc-dir-modal-overlay" onClick={onClose}>
      <div className="pc-dir-modal" onClick={e => e.stopPropagation()}>
        <button className="pc-dir-modal-close" onClick={onClose} aria-label="Cerrar">×</button>

        {item.image_url && <img className="pc-dir-detail-img" src={item.image_url} alt="" />}
        <h3 className="pc-dir-modal-title">{item.title}</h3>
        {item.subtitle && <p className="pc-dir-modal-subtitle">{item.subtitle}</p>}
        {item.meta && <p className="pc-dir-detail-meta">{item.meta}</p>}
        {item.description && <p className="pc-dir-detail-desc">{item.description}</p>}

        {item.link && (
          <a className="pc-dir-connect-btn pc-dir-detail-link" href={item.link} target="_blank" rel="noopener noreferrer">
            Ir a la fuente
          </a>
        )}
      </div>
    </div>
  )
}
