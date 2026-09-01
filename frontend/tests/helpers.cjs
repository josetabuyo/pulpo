// Helper compartido de login para e2e -- reemplaza el viejo login()
// duplicado por archivo que llenaba `.login-box__input` con ADMIN_PASSWORD
// (UI de password que ya no existe, LoginPage.jsx es Google-only desde hace
// rato). Usa el provider "test-login" (web/auth.ts), gateado por
// isLocalDev() -- no existe en ningún build de Vercel, solo corre local.
//
// Réplica del mismo flujo CSRF+POST que hace next-auth/react's signIn() en
// el browser (ver LoginPage.jsx::loginWithGoogle) pero contra el provider
// de test en vez de Google -- nunca navega a una pantalla externa, cero
// interacción de UI necesaria.
async function loginAsAdmin(page, email = 'josetabuyo@gmail.com') {
  const { csrfToken } = await page.request.get('/api/auth/csrf').then(r => r.json())
  const res = await page.request.post('/api/auth/callback/test-login', {
    form: { email, csrfToken, json: 'true' },
  })
  if (!res.ok()) {
    throw new Error(`test-login falló (HTTP ${res.status()}) -- ¿está PULPO_LOCAL_NO_AUTH/isLocalDev() activo en el server de :9010?`)
  }
}

module.exports = { loginAsAdmin }
