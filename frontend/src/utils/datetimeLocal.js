// Conversión entre ISO UTC (backend/API) y el string local que esperan
// los inputs <input type="datetime-local"> (sin offset, "YYYY-MM-DDTHH:mm").

export function isoToLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

export function localInputToIso(value) {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

export function localInputToMs(value) {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.getTime()
}
