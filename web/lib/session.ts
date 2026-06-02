import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { query } from "./db";
import {
  SESSION_COOKIE,
  SESSION_TTL_DAYS,
  generateSessionToken,
  hashToken,
} from "./auth";

export type Role = "admin" | "user";

export interface SessionUser {
  id: number;
  username: string;
  displayName: string;
  role: Role;
  isActive: boolean;
  mustChangePassword: boolean;
}

interface UserRow {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
}

function rowToUser(r: UserRow): SessionUser {
  return {
    id: r.id,
    username: r.username,
    displayName: r.display_name,
    role: r.role,
    isActive: r.is_active,
    mustChangePassword: r.must_change_password,
  };
}

// ── Cookie config ──
// `secure` defaults to true in production; override with COOKIE_SECURE=false
// when deploying over plain HTTP (otherwise the browser won't send the cookie).
function cookieSecure(): boolean {
  if (process.env.COOKIE_SECURE === "true") return true;
  if (process.env.COOKIE_SECURE === "false") return false;
  return process.env.NODE_ENV === "production";
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax" as const,
    path: "/",
    maxAge: SESSION_TTL_DAYS * 24 * 60 * 60,
  };
}

// ── Session lifecycle ──

export async function createSession(userId: number): Promise<string> {
  const token = generateSessionToken();
  const tokenHash = hashToken(token);
  await query(
    `INSERT INTO sessions (token_hash, user_id, expires_at)
     VALUES ($1, $2, now() + ($3 || ' days')::interval)`,
    [tokenHash, userId, String(SESSION_TTL_DAYS)],
  );
  return token;
}

export async function destroySession(token: string): Promise<void> {
  await query("DELETE FROM sessions WHERE token_hash = $1", [hashToken(token)]);
}

// Resolve the user for a raw session token. Enforces expiry and is_active, so a
// disabled user is locked out immediately (no waiting for token expiry).
export async function getUserByToken(token: string | undefined): Promise<SessionUser | null> {
  if (!token) return null;
  const { rows } = await query<UserRow>(
    `SELECT u.id, u.username, u.display_name, u.role, u.is_active, u.must_change_password
       FROM sessions s
       JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = $1 AND s.expires_at > now() AND u.is_active = TRUE`,
    [hashToken(token)],
  );
  return rows[0] ? rowToUser(rows[0]) : null;
}

// For use in server components and route handlers (reads the request cookie).
export async function getCurrentUser(): Promise<SessionUser | null> {
  const store = await cookies();
  return getUserByToken(store.get(SESSION_COOKIE)?.value);
}

// ── Route-handler guards ──

export function unauthorized(): NextResponse {
  return NextResponse.json({ success: false, error: "未登录" }, { status: 401 });
}

export function forbidden(): NextResponse {
  return NextResponse.json({ success: false, error: "无权限" }, { status: 403 });
}

// CSRF defense-in-depth: reject mutating requests whose Origin doesn't match the
// host. Same-origin browser fetches always send a matching Origin on POST/PUT/etc.
export function assertSameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return true; // non-browser / same-origin navigation without Origin
  try {
    const o = new URL(origin);
    const host = req.headers.get("host");
    return !!host && o.host === host;
  } catch {
    return false;
  }
}
