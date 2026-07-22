import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { verifyAccessToken } from "@/lib/auth/jwt";

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

  if (!request.auth?.user) {
    return Response.json({ error: "not authenticated" }, { status: 401 });
  }

  return NextResponse.next();
});

export const config = {
  // Scoped to /api/:path* -- Workflow DevKit's internal resumption requests
  // live under the root /.well-known/workflow/*, so they're never matched
  // here (see node_modules/workflow/docs/getting-started/next.mdx: a broader
  // matcher would need an explicit .well-known/workflow/ exclusion).
  matcher: ["/api/:path*"],
};
