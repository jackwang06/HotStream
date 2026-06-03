import { query } from "./db";

// ── Shared knowledge base (GLOBAL, not per-user) ──────────────────────────
// Every logged-in user can add & view all entries. Editing / deleting /
// enabling is restricted to the creator or an admin (enforced in the route
// handlers via getKnowledgeOwner). Enabled entries are auto-injected into the
// AI copy-generation context.

// Shape returned to the browser by the list endpoint.
export interface KnowledgeItem {
  id: number;
  title: string;
  content: string;
  tags: string;
  enabled: boolean;
  created_by: number | null;
  uploader: string;
  created_at: Date;
  updated_at: Date;
  canEdit: boolean;
}

interface KnowledgeListRow {
  id: number;
  title: string;
  content: string;
  tags: string;
  enabled: boolean;
  created_by: number | null;
  uploader: string;
  created_at: Date;
  updated_at: Date;
}

// All entries (shared), newest-updated first. `uploader` is the creator's
// display name (falling back to username); `canEdit` is true when the current
// user owns the row or is an admin.
export async function listKnowledge(meId: number, isAdmin: boolean): Promise<KnowledgeItem[]> {
  const { rows } = await query<KnowledgeListRow>(
    `SELECT k.id, k.title, k.content, k.tags, k.enabled, k.created_by,
            COALESCE(NULLIF(u.display_name, ''), u.username, '') AS uploader,
            k.created_at, k.updated_at
       FROM knowledge_base k
       LEFT JOIN users u ON u.id = k.created_by
      ORDER BY k.updated_at DESC`,
  );
  return rows.map((r) => ({
    ...r,
    canEdit: isAdmin || r.created_by === meId,
  }));
}

// Enabled entries, used to build the AI injection context.
export async function getEnabledKnowledge(): Promise<{ title: string; content: string }[]> {
  const { rows } = await query<{ title: string; content: string }>(
    `SELECT title, content FROM knowledge_base
      WHERE enabled = TRUE
      ORDER BY updated_at DESC`,
  );
  return rows;
}

interface KnowledgeRow {
  id: number;
  title: string;
  content: string;
  tags: string;
  enabled: boolean;
  created_by: number | null;
  created_at: Date;
  updated_at: Date;
}

export async function createKnowledge(
  createdBy: number,
  fields: { title: string; content: string; tags: string },
): Promise<KnowledgeRow> {
  const { rows } = await query<KnowledgeRow>(
    `INSERT INTO knowledge_base (title, content, tags, created_by)
     VALUES ($1, $2, $3, $4)
     RETURNING id, title, content, tags, enabled, created_by, created_at, updated_at`,
    [fields.title, fields.content, fields.tags, createdBy],
  );
  return rows[0];
}

// Returns the created_by owner id, or `undefined` when the row doesn't exist.
// (created_by itself can be null if the creator's account was deleted.)
export async function getKnowledgeOwner(id: number): Promise<number | null | undefined> {
  const { rows } = await query<{ created_by: number | null }>(
    `SELECT created_by FROM knowledge_base WHERE id = $1`,
    [id],
  );
  return rows.length ? rows[0].created_by : undefined;
}

export async function updateKnowledge(
  id: number,
  fields: { title: string; content: string; tags: string; enabled: boolean },
): Promise<KnowledgeRow | undefined> {
  const { rows } = await query<KnowledgeRow>(
    `UPDATE knowledge_base
        SET title = $1, content = $2, tags = $3, enabled = $4, updated_at = now()
      WHERE id = $5
      RETURNING id, title, content, tags, enabled, created_by, created_at, updated_at`,
    [fields.title, fields.content, fields.tags, fields.enabled, id],
  );
  return rows[0];
}

export async function deleteKnowledge(id: number): Promise<boolean> {
  const { rowCount } = await query(`DELETE FROM knowledge_base WHERE id = $1`, [id]);
  return rowCount > 0;
}
