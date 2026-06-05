// Ensure the first admin account exists (idempotent) and adopt any orphan
// drafts/history rows. Run via `npm run seed:admin` (or the Docker entrypoint,
// after migrate). Reads ADMIN_USERNAME / ADMIN_PASSWORD from the environment.
import { loadEnvConfig } from "@next/env";
import { getPool, query } from "../lib/db";
import { hashPassword } from "../lib/auth";
import { getFactoryDefaultPrompt } from "../lib/prompt-defaults";
import { listPresets, createPreset, setActivePreset } from "../lib/presets";
import { SOULS } from "../lib/prompts";

// Best-effort: ensure a user has the four 代理灵魂 (soul) presets and one selected.
// Idempotent — only seeds when the user currently has zero soul presets.
async function ensureSoulPresets(userId: number): Promise<boolean> {
  const { presets } = await listPresets(userId, "soul");
  if (presets.length > 0) return false;
  let defaultSoulId: number | null = null;
  for (const soul of SOULS) {
    const p = await createPreset(userId, soul.name, soul.content, "soul");
    if (soul.name === "默认") defaultSoulId = p.id;
  }
  if (defaultSoulId != null) await setActivePreset(userId, defaultSoulId);
  return true;
}

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

    // Best-effort: seed admin's 默认提示词 preset if none exist yet.
    try {
      const { presets } = await listPresets(adminId);
      if (presets.length === 0) {
        const seed = await getFactoryDefaultPrompt();
        if (seed) {
          const preset = await createPreset(adminId, "默认", seed);
          await setActivePreset(adminId, preset.id);
          console.log(`[seed-admin] seeded '默认' preset for admin '${username}'`);
        }
      }
    } catch (e) {
      console.warn("[seed-admin] could not seed preset (non-fatal):", (e as Error).message);
    }

    // Adopt any legacy rows that predate per-user scoping so they aren't orphaned.
    const d = await query("UPDATE drafts SET user_id = $1 WHERE user_id IS NULL", [adminId]);
    const h = await query("UPDATE history SET user_id = $1 WHERE user_id IS NULL", [adminId]);
    if (d.rowCount || h.rowCount) {
      console.log(`[seed-admin] adopted ${d.rowCount} orphan draft(s) and ${h.rowCount} orphan history row(s)`);
    }
  }

  // Backfill the four 代理灵魂 (soul) presets for EVERY existing account that
  // doesn't have any yet (so legacy users get 默认/可爱/庄重/活泼 too). Idempotent
  // and best-effort: a single user's failure never aborts the whole pass.
  try {
    const { rows: allUsers } = await query<{ id: number }>("SELECT id FROM users ORDER BY id");
    let seeded = 0;
    for (const u of allUsers) {
      try {
        // Ensure a user_settings row exists so active_soul_preset_id can be set.
        await query("INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", [u.id]);
        if (await ensureSoulPresets(u.id)) seeded++;
      } catch (e) {
        console.warn(`[seed-admin] could not seed soul presets for user ${u.id} (non-fatal):`, (e as Error).message);
      }
    }
    if (seeded) console.log(`[seed-admin] seeded 代理灵魂 presets for ${seeded} account(s)`);
  } catch (e) {
    console.warn("[seed-admin] could not backfill soul presets (non-fatal):", (e as Error).message);
  }

  await getPool().end();
}

main().catch((err) => {
  console.error("[seed-admin] failed:", err);
  process.exit(1);
});
