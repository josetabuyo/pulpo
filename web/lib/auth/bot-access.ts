import { auth } from "@/auth";

// Defense-in-depth for the scoped/"Pulpo Lite" role: proxy.ts is the real
// gate (SCOPED_BOT_ROUTES allowlist), but every route handler a scoped user
// can reach also calls this directly, so a future edit to proxy.ts's regex
// list can't silently turn into a cross-bot data leak on its own.
//
// Returns null when access is allowed (admin, or scoped with this botId in
// their allowlist); otherwise a Response the caller should return as-is.
export async function assertBotAccess(botId: string): Promise<Response | null> {
  const session = await auth();
  const user = session?.user;
  if (!user) return Response.json({ error: "not authenticated" }, { status: 401 });
  if (user.role === "admin") return null;
  if (user.role === "scoped" && user.botIds?.includes(botId)) return null;
  return Response.json({ error: "forbidden" }, { status: 403 });
}
