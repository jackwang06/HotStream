import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { verifyPassword, SESSION_COOKIE } from "@/lib/auth";
import { createSession, sessionCookieOptions, assertSameOrigin } from "@/lib/session";

export const dynamic = "force-dynamic";

const LoginSchema = z.object({
  username: z.string().min(1).max(100),
  password: z.string().min(1).max(200),
});

interface Row {
  id: number;
  password_hash: string;
  is_active: boolean;
  role: "admin" | "user";
  display_name: string;
  username: string;
  must_change_password: boolean;
}

export async function POST(req: Request) {
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof LoginSchema>;
  try {
    body = LoginSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "用户名或密码格式不正确" }, { status: 400 });
  }

  const { rows } = await query<Row>(
    `SELECT id, password_hash, is_active, role, display_name, username, must_change_password
       FROM users WHERE username = $1`,
    [body.username],
  );
  const u = rows[0];
  // Always run verify (with a dummy hash when the user is absent) for constant timing.
  const ok = await verifyPassword(body.password, u?.password_hash);

  if (!u || !ok || !u.is_active) {
    return NextResponse.json({ success: false, error: "用户名或密码错误，或账号已停用" }, { status: 401 });
  }

  const token = await createSession(u.id);
  const res = NextResponse.json({
    success: true,
    user: {
      id: u.id,
      username: u.username,
      displayName: u.display_name,
      role: u.role,
      mustChangePassword: u.must_change_password,
    },
  });
  res.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
  return res;
}
