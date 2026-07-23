// Dónde debe aterrizar cada rol tras loguearse (paso 1 de Pulpo PRO/Lite,
// ver web/auth.ts). admin -> /dashboard. scoped con un bot -> directo a ese
// bot (Lite). scoped con varios -> /bot, selector mínimo (PRO). scoped sin
// ninguno no debería poder pasar signIn en auth.ts, pero por las dudas cae
// a "/" en vez de un loop de redirects.
export function resolveHomePath(user) {
  if (!user) return '/'
  if (user.role === 'admin') return '/dashboard'
  const botIds = user.botIds ?? []
  if (botIds.length === 1) return `/bot/${botIds[0]}`
  if (botIds.length > 1) return '/bot'
  return '/'
}
