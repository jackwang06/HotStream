// Ensure the first admin account exists (idempotent) and adopt any orphan
// drafts/history rows. Run via `npm run seed:admin` (or the Docker entrypoint,
// after migrate). Reads ADMIN_USERNAME / ADMIN_PASSWORD from the environment.
import { loadEnvConfig } from "@next/env";
import { getPool, query } from "../lib/db";
import { hashPassword } from "../lib/auth";

// Load .env.local etc. before any DB connection is opened (getPool is lazy).
loadEnvConfig(process.cwd(), true);

async function main(): Promise<void> {
  const username = (process.env.ADMIN_USERNAME || "").trim();
  const password = process.env.ADMIN_PASSWORD || "";

  if (!username || !password) {
    console.log("[seed-admin] ADMIN_USERNAME / ADMIN_PASSWORD not set — skipping admin seed");
  } else {
    const existing = await query<{ id: number }>("SELECT id FROM users WHERE username = $1", [username]);
    let adminId: number;
    if (existing.rows.length > 0) {
      adminId = existing.rows[0].id;
      // Make sure the configured admin is actually an active admin.
      await query("UPDATE users SET role = 'admin', is_active = TRUE, updated_at = now() WHERE id = $1", [adminId]);
      console.log(`[seed-admin] admin '${username}' already exists (id=${adminId}); ensured active admin role`);
    } else {
      const hash = await hashPassword(password);
      const inserted = await query<{ id: number }>(
        "INSERT INTO users (username, password_hash, display_name, role, is_active) VALUES ($1, $2, $3, 'admin', TRUE) RETURNING id",
        [username, hash, username],
      );
      adminId = inserted.rows[0].id;
      console.log(`[seed-admin] created admin '${username}' (id=${adminId})`);
    }

    await query("INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", [adminId]);

    // Adopt any legacy rows that predate per-user scoping so they aren't orphaned.
    const d = await query("UPDATE drafts SET user_id = $1 WHERE user_id IS NULL", [adminId]);
    const h = await query("UPDATE history SET user_id = $1 WHERE user_id IS NULL", [adminId]);
    if (d.rowCount || h.rowCount) {
      console.log(`[seed-admin] adopted ${d.rowCount} orphan draft(s) and ${h.rowCount} orphan history row(s)`);
    }
  }

  await getPool().end();
}

main().catch((err) => {
  console.error("[seed-admin] failed:", err);
  process.exit(1);
});
