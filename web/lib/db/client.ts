import { drizzle as drizzleNeonHttp, type NeonHttpDatabase } from "drizzle-orm/neon-http";
import { drizzle as drizzlePg, type NodePgDatabase } from "drizzle-orm/node-postgres";
import { neon } from "@neondatabase/serverless";
import { Pool } from "pg";
import * as schema from "./schema";

// Lazy-initialized so `next build`'s page-data collection (which imports
// every route module) doesn't require DATABASE_URL to be set -- only
// runtime requests that actually touch the DB do. Plain function, not a
// Proxy wrapper (a Proxy around the client breaks libraries that inspect the
// object directly, e.g. introspecting method existence).
//
// Dual driver (2026-07-22): production/preview always point at real Neon
// (neon-http, HTTP-based, what Vercel's serverless functions need). Local
// dev now points at a genuinely local Postgres (see
// management/HANDOFF_VERCEL_DEEP_MIGRATION.md, "Base de datos local para
// dev") -- a plain postgres:// URL that isn't a Neon hostname, so it needs
// the standard node-postgres driver instead (Neon's HTTP driver can't talk
// to a non-Neon Postgres). Both return Drizzle's common query builder API,
// so every caller in lib/business/*.ts is unaffected either way.
type Db = NeonHttpDatabase<typeof schema> | NodePgDatabase<typeof schema>;

function createDb(): Db {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  if (url.includes(".neon.tech")) {
    return drizzleNeonHttp(neon(url), { schema });
  }
  const pool = new Pool({ connectionString: url });
  return drizzlePg(pool, { schema });
}

let instance: Db | null = null;

export function getDb(): Db {
  if (!instance) instance = createDb();
  return instance;
}
