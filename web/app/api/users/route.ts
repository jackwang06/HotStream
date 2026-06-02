import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { getCurrentUser, unauthorized, forbidden, assertSameOrigin } from "@/lib/session";
import { listUsers } from "@/lib/users";
import { hashPassword } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (user.role !== "admin") return forbidden();
  return NextResponse.json({ success: true, users: await listUsers() });
}

const CreateSchema = z.object({
  username: z.string().trim().min(1).max(100),
  password: z.string().min(6).max(200),
  displayName: z.string().max(200).optional().default(""),
  role: z.enum(["admin", "user"]).optional().default("user"),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (user.role !== "admin") return forbidden();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof CreateSchema>;
  try {
    body = CreateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "用户名/密码格式不正确（密码至少 6 位）" }, { status: 400 });
  }

  const hash = await hashPassword(body.password);
  try {
    const { rows } = await query<{ id: number }>(
      `INSERT INTO users (username, password_hash, display_name, role, is_active)
       VALUES ($1, $2, $3, $4, TRUE) RETURNING id`,
      [body.username, hash, body.displayName || body.username, body.role],
    );
    const id = rows[0].id;
    await query("INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", [id]);
    return NextResponse.json({ success: true, id });
  } catch (e) {
    // 23505 = unique_violation (duplicate username)
    if ((e as { code?: string }).code === "23505") {
      return NextResponse.json({ success: false, error: "用户名已存在" }, { status: 409 });
    }
    return NextResponse.json({ success: false, error: "创建失败" }, { status: 500 });
  }
}
