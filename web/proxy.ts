import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { verifyAccessToken } from "@/lib/auth/jwt";
import { isLocalNoAuth } from "@/lib/auth/local-bypass";

// Fixes the root-cause auth bug found in pulpo/interfaces/ui/app.py: there,
// `app.mount("/api", api)` creates a separate Starlette sub-app that the
// parent's `Depends` never reaches, so 9/10 routers ended up with zero real
// auth despite comments claiming otherwise. Here, proxy runs for every
// matched request BEFORE any route handler, so there's no equivalent gap --
// a route can't "forget" to import a dependency because the check never
// lived in the route in the first place.
//
// Two auth schemes on purpose, not leftover mess: /api/flows/*/trigger/* is a
// webhook-style external trigger (pulpo/graphs/nodes/api_trigger.py has no
// concept of a browser session), so it stays on the JWT bearer scheme
// (lib/auth/jwt.ts, /api/auth/token). Everything else is a human at the
// admin dashboard, gated by a real Google session (auth.ts, Auth.js v5) --
// same pattern as Luganense's middleware.ts.
//
// /api/telegram/webhook/* is a THIRD scheme: Telegram sends neither a
// session cookie nor a bearer token, so this path is public here -- the
// route itself verifies the tokenId in the URL against telegram_connections
// (and an optional secret_token header), see that route's docstring.
const TRIGGER_PATH_RE = /^\/api\/flows\/[^/]+\/trigger\/[^/]+$/;
const TELEGRAM_WEBHOOK_RE = /^\/api\/telegram\/webhook\/[^/]+$/;
const PUBLIC_PATHS = ["/api/auth/token"];

// Paso 1 hacia Pulpo PRO/Lite (2026-07-22, ver auth.ts): allowlist explícita
// y method-aware de qué puede pegar un usuario "scoped" (bot_users), UNA vez
// que el botId en el path esté en su session.user.botIds. Cada entrada tiene
// exactamente UN grupo de captura = el botId a comparar.
//
// Deliberadamente NO se usa una regla laxa tipo "si el path contiene algún
// botId de la lista" -- eso sería explotable: /api/bots/A/users contiene "A"
// y colaría el tab de gestión de usuarios (otorgar acceso es acción de
// admin, no de un scoped sobre sí mismo); un `number` de conexión de
// WhatsApp podría coincidir por casualidad con un botId; y no distinguiría
// un bot ajeno si aparece como substring en otra parte del path. Por eso:
// método exacto + regex anclada (^...$) que captura el segmento específico +
// comparación exacta con `.includes()` contra botIds.
//
// Fuera de esta allowlist a propósito (quedan solo para "admin"):
// GET/POST /api/bots (plural, lista todo), PUT/DELETE /api/bots/{id} (editar
// nombre / borrar bot), /api/bots/{id}/users/** (otorgar acceso es admin-only,
// aunque sea sobre el propio bot), /api/connections/** (keyed por `number`,
// no por botId -- no se puede autorizar de forma segura acá), /api/runs*
// (no filtra por bot todavía), /api/config/settings, /api/wavi/*, y las
// sub-rutas de versions/node-flows de flows (no portadas a este paso).
const SCOPED_BOT_ROUTES: { method: string; re: RegExp }[] = [
  { method: "GET", re: /^\/api\/bots\/([^/]+)$/ },
  { method: "GET", re: /^\/api\/bot\/([^/]+)\/paused$/ },
  { method: "PUT", re: /^\/api\/bot\/([^/]+)\/paused$/ },
  { method: "POST", re: /^\/api\/bot\/([^/]+)\/telegram$/ },
  { method: "DELETE", re: /^\/api\/bot\/([^/]+)\/telegram\/[^/]+$/ },
  { method: "PATCH", re: /^\/api\/bots\/([^/]+)\/telegram\/[^/]+\/settings$/ },
  { method: "GET", re: /^\/api\/bots\/([^/]+)\/google-connections$/ },
  { method: "POST", re: /^\/api\/bots\/([^/]+)\/google-connections$/ },
  { method: "DELETE", re: /^\/api\/bots\/([^/]+)\/google-connections\/[^/]+$/ },
  { method: "GET", re: /^\/api\/flows\/bots\/([^/]+)$/ },
  { method: "POST", re: /^\/api\/flows\/bots\/([^/]+)$/ },
  { method: "GET", re: /^\/api\/flows\/bots\/([^/]+)\/[^/]+$/ },
  { method: "PUT", re: /^\/api\/flows\/bots\/([^/]+)\/[^/]+$/ },
  { method: "DELETE", re: /^\/api\/flows\/bots\/([^/]+)\/[^/]+$/ },
  { method: "GET", re: /^\/api\/flows\/bots\/([^/]+)\/has-node\/[^/]+$/ },
];

export default auth(async (request) => {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.includes(pathname) || pathname.startsWith("/api/auth/") || TELEGRAM_WEBHOOK_RE.test(pathname)) {
    return NextResponse.next();
  }

  if (TRIGGER_PATH_RE.test(pathname)) {
    const authHeader = request.headers.get("authorization") || "";
    const token = authHeader.startsWith("Bearer ") ? authHeader.slice("Bearer ".length) : null;
    if (!token || !(await verifyAccessToken(token))) {
      return Response.json({ error: "missing or invalid bearer token" }, { status: 401 });
    }
    return NextResponse.next();
  }

  // No-auth CLI bypass for local dev (management/HANDOFF_LOCAL_CLI_AND_NODES.md
  // §4.3) -- see lib/auth/local-bypass.ts for the three-condition predicate
  // (never Vercel + explicit opt-in env var + loopback host). Placed here,
  // after the public/bearer schemes above (unchanged) and before the
  // session gate below -- when it fires, the request proceeds as if it were
  // an authenticated admin, without touching auth.ts or forging a session.
  if (isLocalNoAuth(request)) {
    return NextResponse.next();
  }

  if (!request.auth?.user) {
    return Response.json({ error: "not authenticated" }, { status: 401 });
  }

  // Paso 2 hacia Pulpo PRO/Lite (2026-07-22, ver auth.ts): admin ve todo,
  // como siempre. "scoped" solo pasa si el método+path matchea una entrada
  // de SCOPED_BOT_ROUTES Y el botId capturado está en su session.botIds --
  // cualquier otra cosa (incluido un botId ajeno) es 403. Ver el comentario
  // de SCOPED_BOT_ROUTES arriba para el razonamiento de seguridad.
  if (request.auth.user.role === "admin") {
    return NextResponse.next();
  }

  const botIds = request.auth.user.botIds ?? [];
  for (const { method, re } of SCOPED_BOT_ROUTES) {
    if (request.method !== method) continue;
    const match = re.exec(pathname);
    if (!match) continue;
    if (botIds.includes(match[1])) return NextResponse.next();
    return Response.json({ error: "forbidden" }, { status: 403 }); // bot ajeno
  }
  return Response.json({ error: "forbidden" }, { status: 403 }); // ruta no habilitada para scoped
});

export const config = {
  // Scoped to /api/:path* -- Workflow DevKit's internal resumption requests
  // live under the root /.well-known/workflow/*, so they're never matched
  // here (see node_modules/workflow/docs/getting-started/next.mdx: a broader
  // matcher would need an explicit .well-known/workflow/ exclusion).
  matcher: ["/api/:path*"],
};
