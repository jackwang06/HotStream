// Idempotent DB migration. Run via `npm run migrate` (or the Docker entrypoint).
// Wrapped in a Postgres advisory lock so concurrent instances can't race the DDL.
import { loadEnvConfig } from "@next/env";
import { getPool } from "../lib/db";
import { SCHEMA_SQL } from "../lib/schema";

// Load .env.local etc. before any DB connection is opened (getPool is lazy).
// In Docker, real env vars are provided directly and this is a harmless no-op.
loadEnvConfig(process.cwd(), true);

const LOCK_KEY = 918_273_645; // arbitrary constant shared by all migrators

async function main(): Promise<void> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query("SELECT pg_advisory_lock($1)", [LOCK_KEY]);
    await client.query(SCHEMA_SQL);
    console.log("[migrate] schema applied (idempotent)");
  } finally {
    await client.query("SELECT pg_advisory_unlock($1)", [LOCK_KEY]).catch(() => {});
    client.release();
    await pool.end();
  }
}

main().catch((err) => {
  console.error("[migrate] failed:", err);
  process.exit(1);
});
