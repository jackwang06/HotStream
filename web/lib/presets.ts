import { query } from "./db";

// ── Named prompt presets (per-user) ───────────────────────────────────────
// Each user owns an unlimited number of named presets, split into two kinds:
//   kind='default' → 「默认提示词」类：starting point for the homepage prompt.
//                    user_settings.active_preset_id points at the selected one.
//   kind='soul'    → 「代理灵魂」类：the AI system persona (global_prompt).
//                    user_settings.active_soul_preset_id points at the selected one.
// The "effective default prompt" resolves: active default preset → legacy
// user_settings.default_prompt → "". The "effective soul" resolves: active soul
// preset → legacy user_settings.global_prompt → "" (backend supplies its own).

export type PresetKind = "default" | "soul";

export interface PresetRow {
  id: number;
  name: string;
  content: string;
  kind: PresetKind;
  created_at: Date;
  updated_at: Date;
}

// All of the user's presets of the given kind (newest-updated first) plus the
// currently selected ids for BOTH kinds (so callers can show the right "active").
export async function listPresets(
  userId: number,
  kind: PresetKind = "default",
): Promise<{
  presets: PresetRow[];
  activePresetId: number | null;
  activeSoulPresetId: number | null;
}> {
  const { rows } = await query<PresetRow>(
    `SELECT id, name, content, kind, created_at, updated_at
       FROM prompt_presets WHERE user_id = $1 AND kind = $2
      ORDER BY updated_at DESC`,
    [userId, kind],
  );
  const { rows: settingsRows } = await query<{
    active_preset_id: number | null;
    active_soul_preset_id: number | null;
  }>(
    `SELECT active_preset_id, active_soul_preset_id FROM user_settings WHERE user_id = $1`,
    [userId],
  );
  const activePresetId = settingsRows[0]?.active_preset_id ?? null;
  const activeSoulPresetId = settingsRows[0]?.active_soul_preset_id ?? null;
  return { presets: rows, activePresetId, activeSoulPresetId };
}

// Create a new preset owned by `userId`. Returns the new row.
export async function createPreset(
  userId: number,
  name: string,
  content: string,
  kind: PresetKind = "default",
): Promise<PresetRow> {
  const { rows } = await query<PresetRow>(
    `INSERT INTO prompt_presets (user_id, name, content, kind)
     VALUES ($1, $2, $3, $4)
     RETURNING id, name, content, kind, created_at, updated_at`,
    [userId, name, content, kind],
  );
  return rows[0];
}

// Update name/content of the caller's own preset. `undefined` fields are left
// unchanged (COALESCE). Returns true when a row was updated (i.e. it existed
// and belonged to the user). kind is immutable once created.
export async function updatePreset(
  userId: number,
  id: number,
  fields: { name?: string; content?: string },
): Promise<boolean> {
  const name = fields.name ?? null;
  const content = fields.content ?? null;
  const { rowCount } = await query(
    `UPDATE prompt_presets
        SET name       = COALESCE($1, name),
            content    = COALESCE($2, content),
            updated_at = now()
      WHERE id = $3 AND user_id = $4`,
    [name, content, id, userId],
  );
  return rowCount > 0;
}

// Returns the owner userId, or `undefined` when the row doesn't exist.
// (Mirrors knowledge.ts getKnowledgeOwner. user_id is NOT NULL, so an existing
// row never yields null — the null arm is kept only to match that signature.)
export async function getPresetOwner(id: number): Promise<number | null | undefined> {
  const { rows } = await query<{ user_id: number }>(
    `SELECT user_id FROM prompt_presets WHERE id = $1`,
    [id],
  );
  return rows.length ? rows[0].user_id : undefined;
}

// The kind of a preset, or undefined when the row doesn't exist.
export async function getPresetKind(id: number): Promise<PresetKind | undefined> {
  const { rows } = await query<{ kind: PresetKind }>(
    `SELECT kind FROM prompt_presets WHERE id = $1`,
    [id],
  );
  return rows.length ? rows[0].kind : undefined;
}

// Delete the caller's own preset. If it was the active one (either kind), the FK
// `ON DELETE SET NULL` automatically clears the matching user_settings column.
// Returns true when a row was deleted.
export async function deletePreset(userId: number, id: number): Promise<boolean> {
  const { rowCount } = await query(
    `DELETE FROM prompt_presets WHERE id = $1 AND user_id = $2`,
    [id, userId],
  );
  return rowCount > 0;
}

// Set the user's active preset. Looks up the preset's kind and writes the
// corresponding column (active_soul_preset_id for kind='soul', else
// active_preset_id). The id is only applied when it belongs to the user;
// pointing at someone else's / a missing preset is a no-op.
export async function setActivePreset(userId: number, id: number): Promise<void> {
  const kind = await getPresetKind(id);
  const column = kind === "soul" ? "active_soul_preset_id" : "active_preset_id";
  await query(
    `UPDATE user_settings
        SET ${column} = $2, updated_at = now()
      WHERE user_id = $1
        AND EXISTS (SELECT 1 FROM prompt_presets WHERE id = $2 AND user_id = $1)`,
    [userId, id],
  );
}

// The "effective default prompt": active default preset content → legacy
// user_settings.default_prompt → "". Resolved server-side in a single query.
export async function getActivePresetContent(userId: number): Promise<string> {
  const { rows } = await query<{ preset_content: string | null; default_prompt: string | null }>(
    `SELECT p.content AS preset_content, s.default_prompt AS default_prompt
       FROM user_settings s
       LEFT JOIN prompt_presets p
         ON p.id = s.active_preset_id AND p.user_id = s.user_id
      WHERE s.user_id = $1`,
    [userId],
  );
  const row = rows[0];
  if (!row) return "";
  if (row.preset_content != null) return row.preset_content;
  return row.default_prompt ?? "";
}

// The "effective soul" (代理灵魂 / system persona): active soul preset content →
// legacy user_settings.global_prompt → "" (backend supplies its own default).
// Resolved server-side in a single query.
export async function getActiveSoulContent(userId: number): Promise<string> {
  const { rows } = await query<{ preset_content: string | null; global_prompt: string | null }>(
    `SELECT p.content AS preset_content, s.global_prompt AS global_prompt
       FROM user_settings s
       LEFT JOIN prompt_presets p
         ON p.id = s.active_soul_preset_id AND p.user_id = s.user_id
      WHERE s.user_id = $1`,
    [userId],
  );
  const row = rows[0];
  if (!row) return "";
  if (row.preset_content != null) return row.preset_content;
  return row.global_prompt ?? "";
}
