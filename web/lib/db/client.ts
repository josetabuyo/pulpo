import { drizzle, type NeonHttpDatabase } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";
import * as schema from "./schema";

// Lazy-initialized so `next build`'s page-data collection (which imports
// every route module) doesn't require DATABASE_URL to be set -- only
// runtime requests that actually touch the DB do. Plain function, not a
// Proxy wrapper (a Proxy around the client breaks libraries that inspect the
// object directly, e.g. introspecting method existence).
function createDb() {
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL is not set");
  return drizzle(neon(process.env.DATABASE_URL), { schema });
}

let instance: NeonHttpDatabase<typeof schema> | null = null;

export function getDb(): NeonHttpDatabase<typeof schema> {
  if (!instance) instance = createDb();
  return instance;
}
