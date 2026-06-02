import { query } from "./db";
import type { Role } from "./session";

export interface UserListRow {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: Date;
}

export async function listUsers(): Promise<UserListRow[]> {
  const { rows } = await query<UserListRow>(
    `SELECT id, username, display_name, role, is_active, created_at
       FROM users ORDER BY id ASC`,
  );
  return rows;
}

// Number of OTHER active admins (excluding the given user id). Used to prevent
// removing/demoting/deactivating the last remaining admin.
export async function countOtherActiveAdmins(excludeId: number): Promise<number> {
  const { rows } = await query<{ n: string }>(
    `SELECT count(*)::text AS n FROM users WHERE role = 'admin' AND is_active = TRUE AND id <> $1`,
    [excludeId],
  );
  return Number(rows[0]?.n ?? "0");
}

export async function getUserRowById(id: number): Promise<{ id: number; role: Role; is_active: boolean } | null> {
  const { rows } = await query<{ id: number; role: Role; is_active: boolean }>(
    `SELECT id, role, is_active FROM users WHERE id = $1`,
    [id],
  );
  return rows[0] ?? null;
}

// Invalidate all sessions for a user (used on password reset / deactivation).
export async function deleteUserSessions(userId: number): Promise<void> {
  await query("DELETE FROM sessions WHERE user_id = $1", [userId]);
}
