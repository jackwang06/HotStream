import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { getCurrentUser, unauthorized, forbidden, assertSameOrigin } from "@/lib/session";
import { listUsers } from "@/lib/users";
import { hashPassword } from "@/lib/auth";
import { getFactoryDefaultPrompt } from "@/lib/prompt-defaults";
import { createPreset, setActivePreset } from "@/lib/presets";
import { SOULS } from "@/lib/prompts";

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

    // Best-effort: seed the new user with a "默认" 默认提示词 preset (factory template).
    try {
      const seed = await getFactoryDefaultPrompt();
      if (seed) {
        const preset = await createPreset(id, "默认", seed);
        await setActivePreset(id, preset.id);
      }
    } catch {
      // Seed failure must not prevent account creation from succeeding.
    }

    // Best-effort: seed the four 代理灵魂 (soul) presets, selecting "默认".
    try {
      let defaultSoulId: number | null = null;
      for (const soul of SOULS) {
        const p = await createPreset(id, soul.name, soul.content, "soul");
        if (soul.name === "默认") defaultSoulId = p.id;
      }
      if (defaultSoulId != null) await setActivePreset(id, defaultSoulId);
    } catch {
      // Seed failure must not prevent account creation from succeeding.
    }

    return NextResponse.json({ success: true, id });
  } catch (e) {
    // 23505 = unique_violation (duplicate username)
    if ((e as { code?: string }).code === "23505") {
      return NextResponse.json({ success: false, error: "用户名已存在" }, { status: 409 });
    }
    return NextResponse.json({ success: false, error: "创建失败" }, { status: 500 });
  }
}
