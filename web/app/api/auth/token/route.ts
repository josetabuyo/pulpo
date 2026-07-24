import { createAccessToken } from "@/lib/auth/jwt";

// Minimal, real, server-validated login -- deliberately NOT the pattern in
// pulpo/interfaces/ui/src/pages/LoginPage.jsx, which only checks locally and
// caches the raw password in sessionStorage while trusting the (unprotected)
// backend to reject bad requests. Here the check is server-side and the
// issued JWT is what proxy.ts actually verifies on every other /api/* route.
// Spike-scoped: a single shared ADMIN_PASSWORD, not the bot-level
// password/session scheme from pulpo/core/auth_jwt.py -- that gets ported in
// the full migration, not here.
export async function POST(request: Request) {
  const { password } = await request.json();

  if (!process.env.ADMIN_PASSWORD) {
    return Response.json({ error: "ADMIN_PASSWORD is not configured" }, { status: 500 });
  }

  if (password !== process.env.ADMIN_PASSWORD) {
    return Response.json({ error: "invalid password" }, { status: 401 });
  }

  const token = await createAccessToken("admin");
  return Response.json({ access_token: token });
}
