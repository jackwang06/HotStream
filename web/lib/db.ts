import { Pool, type PoolClient, type QueryResultRow } from "pg";

// All HotStream tables live in this schema; the DB user has NO rights on `public`.
export function getSchema(): string {
  return process.env.DB_SCHEMA || "wangyafei";
}

function createPool(): Pool {
  const schema = getSchema();
  return new Pool({
    host: process.env.DB_HOST,
    port: Number(process.env.DB_PORT || "5432"),
    database: process.env.DB_NAME,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    max: 10,
    connectionTimeoutMillis: 10_000,
    idleTimeoutMillis: 30_000,
    // Lock search_path at connection startup. Passed as a libpq startup option,
    // so it sticks for the life of each pooled backend (more reliable than a
    // per-checkout `SET search_path`, and survives PgBouncer transaction pooling).
    options: `-c search_path=${schema}`,
  });
}

// Singleton across dev HMR so we don't leak connection pools on hot reload.
const globalForPool = globalThis as unknown as { __hotstreamPool?: Pool };

export function getPool(): Pool {
  if (!globalForPool.__hotstreamPool) {
    globalForPool.__hotstreamPool = createPool();
  }
  return globalForPool.__hotstreamPool;
}

export async function query<T extends QueryResultRow = QueryResultRow>(
  text: string,
  params: unknown[] = [],
): Promise<{ rows: T[]; rowCount: number }> {
  const res = await getPool().query<T>(text, params);
  return { rows: res.rows, rowCount: res.rowCount ?? 0 };
}

// Run a function inside a single dedicated connection (e.g. to hold an advisory
// lock or a transaction across multiple statements).
export async function withClient<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await getPool().connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}
