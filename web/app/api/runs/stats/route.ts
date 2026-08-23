import { getRunStats } from "@/lib/business/run-stats";
import { assertBotAccess } from "@/lib/auth/bot-access";
import { isLocalNoAuth } from "@/lib/auth/local-bypass";
import { auth } from "@/auth";

// GET /api/runs/stats?since=1h&bucket=5[&botId=] -- bucketed success/error/pending
// counts for the Monitor panel's overlapping chart. `since` accepts a
// duration string ("15m"|"1h"|"6h"|"24h"|"7d"); `bucket` is the bucket size
// in minutes (defaults scale with the window if omitted).
//
// `botId` no está en el path (proxy.ts::SELF_VALIDATING_ROUTES lo deja pasar
// con solo sesión), así que el chequeo real es acá: sin `botId` es el
// Monitor global del dashboard admin (DashboardPage.jsx), admin-only; con
// `botId` es el Monitor del tab "Ejecuciones" de un bot puntual
// (RunsTab.jsx), mismo criterio que cualquier otra pantalla del bot.
const DURATION_RE = /^(\d+)(m|h|d)$/;

function parseDurationMinutes(value: string | null, fallbackMinutes: number): number {
  if (!value) return fallbackMinutes;
  const match = DURATION_RE.exec(value);
  if (!match) return fallbackMinutes;
  const amount = Number(match[1]);
  const unit = match[2];
  if (unit === "m") return amount;
  if (unit === "h") return amount * 60;
  return amount * 60 * 24;
}

function defaultBucketMinutes(windowMinutes: number): number {
  if (windowMinutes <= 60) return 1;
  if (windowMinutes <= 6 * 60) return 5;
  if (windowMinutes <= 24 * 60) return 30;
  return 60 * 4; // 7d window -> 4h buckets
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const windowMinutes = parseDurationMinutes(searchParams.get("since"), 60);
  const bucketMinutes = Number(searchParams.get("bucket")) || defaultBucketMinutes(windowMinutes);
  const botId = searchParams.get("botId") ?? undefined;

  if (botId) {
    const denied = await assertBotAccess(request, botId);
    if (denied) return denied;
  } else if (!isLocalNoAuth(request)) {
    const session = await auth();
    if (session?.user?.role !== "admin") {
      return Response.json({ error: "forbidden" }, { status: 403 });
    }
  }

  const since = new Date(Date.now() - windowMinutes * 60 * 1000);
  const stats = await getRunStats({ since, bucketMinutes, botId });
  return Response.json(stats);
}
