import { auth } from "@/auth";
import { isLocalNoAuth } from "./local-bypass";
import { isSyncTokenRequest } from "./sync-token";
import { isBotKeyRequest } from "./bot-key";

// Defense-in-depth for the scoped/"Pulpo Lite" role: proxy.ts is the real
// gate (SCOPED_BOT_ROUTES allowlist), but every route handler a scoped user
// can reach also calls this directly, so a future edit to proxy.ts's regex
// list can't silently turn into a cross-bot data leak on its own.
//
// Local no-auth CLI bypass (2026-07-23, management/HANDOFF_LOCAL_CLI_AND_NODES.md
// §4.3): proxy.ts's own isLocalNoAuth() check lets the request past the
// middleware with no `auth.user` at all -- without the check below, every
// route that calls assertBotAccess() would then reject it as "not
// authenticated" despite proxy.ts having already decided to let it through.
// One predicate (lib/auth/local-bypass.ts), two consumers, so the three
// conditions never drift out of sync between proxy.ts and here.
//
// Returns null when access is allowed (admin, scoped with this botId in
// their allowlist, or the local no-auth bypass is active for this request);
// otherwise a Response the caller should return as-is.
export async function assertBotAccess(request: Request, botId: string): Promise<Response | null> {
  if (isLocalNoAuth(request)) return null;

  const session = await auth();
  const user = session?.user;
  if (!user) return Response.json({ error: "not authenticated" }, { status: 401 });
  if (user.role === "admin") return null;
  if (user.role === "scoped" && user.botIds?.includes(botId)) return null;
  return Response.json({ error: "forbidden" }, { status: 403 });
}

// Compuesto usado SOLO por las rutas de flows que un ambiente remoto puede
// llamar (list/get/push, ver proxy.ts::SYNC_TOKEN_ROUTES) -- deliberadamente
// no es el default de assertBotAccess de arriba, para no filtrar el
// sync-token a rutas no relacionadas (chat-configs, google-connections,
// etc.) que también llaman assertBotAccess.
export async function assertBotAccessOrSyncToken(request: Request, botId: string): Promise<Response | null> {
  if (isSyncTokenRequest(request)) return null;
  return assertBotAccess(request, botId);
}

// Compuesto usado por el reporte público de test (2026-08-07, ver
// lib/business/test-report-publish.ts / proxy.ts::BOT_KEY_ROUTES): a
// diferencia del sync-token (un secreto global de instancia, para OTRO
// ambiente Pulpo), acá el caller externo es un tercero (ej. el sitio del
// cliente) leyendo SOLO los reportes de SU bot -- por eso usa el secreto
// por-bot (lib/auth/bot-key.ts) en vez de ensanchar assertBotAccessOrSyncToken.
export async function assertBotAccessOrBotKey(request: Request, botId: string): Promise<Response | null> {
  if (await isBotKeyRequest(request, botId)) return null;
  return assertBotAccess(request, botId);
}
