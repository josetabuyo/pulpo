import { getRunStats } from "@/lib/business/run-stats";

// GET /api/runs/stats?since=1h&bucket=5 -- bucketed success/error/pending
// counts for the Monitor panel's overlapping chart. `since` accepts a
// duration string ("15m"|"1h"|"6h"|"24h"|"7d"); `bucket` is the bucket size
// in minutes (defaults scale with the window if omitted).
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

  const since = new Date(Date.now() - windowMinutes * 60 * 1000);
  const stats = await getRunStats({ since, bucketMinutes });
  return Response.json(stats);
}
