import { eq } from "drizzle-orm";
import { getDb } from "@/lib/db/client";
import { settings } from "@/lib/db/schema";

// TS port of pulpo/business/settings.py -- config-only, single row.
const ROW_ID = "singleton";

export async function getSettings(): Promise<{ wa_poll_interval_seconds: number }> {
  const db = getDb();
  const [row] = await db.select().from(settings).where(eq(settings.id, ROW_ID));
  return { wa_poll_interval_seconds: Number(row?.waPollIntervalSeconds ?? 300) };
}

export async function updateSettings(patch: {
  wa_poll_interval_seconds?: number;
}): Promise<{ wa_poll_interval_seconds: number }> {
  const db = getDb();
  if (patch.wa_poll_interval_seconds != null) {
    const v = Math.max(60, Math.min(3600, Math.round(patch.wa_poll_interval_seconds)));
    await db
      .insert(settings)
      .values({ id: ROW_ID, waPollIntervalSeconds: String(v) })
      .onConflictDoUpdate({ target: settings.id, set: { waPollIntervalSeconds: String(v) } });
  }
  return getSettings();
}
