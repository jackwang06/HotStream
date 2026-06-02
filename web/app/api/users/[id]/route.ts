import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { getCurrentUser, unauthorized, forbidden, assertSameOrigin } from "@/lib/session";
import { hashPassword } from "@/lib/auth";
import { getUserRowById, deleteUserSessions } from "@/lib/users";

export const dynamic = "force-dynamic";

function parseId(idStr: string): number | null {
  const id = Number(idStr);
  return Number.isInteger(id) && id > 0 ? id : null;
}

const PatchSchema = z.object({
  isActive: z.boolean().optional(),
  role: z.enum(["admin", "user"]).optional(),
  password: z.string().min(6).max(200).optional(),
  displayName: z.string().max(200).optional(),
});

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const me = await getCurrentUser();
  if (!me) return unauthorized();
  if (me.role !== "admin") return forbidden();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的用户 ID" }, { status: 400 });

  let body: z.infer<typeof PatchSchema>;
  try {
    body = PatchSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确（密码至少 6 位）" }, { status: 400 });
  }

  const target = await getUserRowById(id);
  if (!target) return NextResponse.json({ success: false, error: "用户不存在" }, { status: 404 });

  const deny = (msg: string) => NextResponse.json({ success: false, error: msg }, { status: 409 });

  // Self-lockout guards (not racy — me.id is fixed).
  if (body.isActive === false && id === me.id) return deny("不能停用自己");
  if (body.role === "user" && target.role === "admin" && id === me.id) return deny("不能降级自己的角色");

  const sets: string[] = [];
  const vals: unknown[] = [];
  let i = 1;
  if (body.displayName !== undefined) { sets.push(`display_name = $${i++}`); vals.push(body.displayName); }
  if (body.role !== undefined) { sets.push(`role = $${i++}`); vals.push(body.role); }
  if (body.isActive !== undefined) { sets.push(`is_active = $${i++}`); vals.push(body.isActive); }
  let passwordChanged = false;
  if (body.password !== undefined) {
    sets.push(`password_hash = $${i++}`);
    vals.push(await hashPassword(body.password));
    passwordChanged = true;
  }
  if (sets.length === 0) {
    return NextResponse.json({ success: false, error: "没有要更新的字段" }, { status: 400 });
  }
  sets.push("updated_at = now()");

  // Last-admin protection enforced ATOMICALLY inside the WHERE clause so a
  // concurrent demote/deactivate of two admins can't both slip through.
  const removesAdminPower = body.isActive === false || (body.role === "user" && target.role === "admin");
  const idParam = i; // $i references the target id (reused by the EXISTS guard)
  vals.push(id);
  let where = `id = $${idParam}`;
  if (removesAdminPower) {
    where += ` AND EXISTS (SELECT 1 FROM users WHERE role = 'admin' AND is_active = TRUE AND id <> $${idParam})`;
  }

  const res = await query(`UPDATE users SET ${sets.join(", ")} WHERE ${where}`, vals);
  if (res.rowCount === 0) {
    if (removesAdminPower) return deny("不能停用/降级最后一个管理员");
    return NextResponse.json({ success: false, error: "用户不存在" }, { status: 404 });
  }

  // Force re-login when the password changes or the account is deactivated.
  if (passwordChanged || body.isActive === false) {
    await deleteUserSessions(id);
  }
  return NextResponse.json({ success: true });
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const me = await getCurrentUser();
  if (!me) return unauthorized();
  if (me.role !== "admin") return forbidden();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的用户 ID" }, { status: 400 });

  const deny = (msg: string) => NextResponse.json({ success: false, error: msg }, { status: 409 });
  if (id === me.id) return deny("不能删除自己");

  try {
    // Atomic: refuse to delete the last active admin (the EXISTS guard runs in
    // the same statement, so two concurrent deletes can't both succeed).
    const res = await query(
      `DELETE FROM users
        WHERE id = $1
          AND (role <> 'admin' OR is_active = FALSE
               OR EXISTS (SELECT 1 FROM users WHERE role = 'admin' AND is_active = TRUE AND id <> $1))`,
      [id],
    );
    if (res.rowCount === 0) {
      const still = await getUserRowById(id);
      if (still) return deny("不能删除最后一个管理员");
      return NextResponse.json({ success: false, error: "用户不存在" }, { status: 404 });
    }
    return NextResponse.json({ success: true });
  } catch (e) {
    // 23503 = foreign_key_violation: user still owns drafts/history (ON DELETE RESTRICT)
    if ((e as { code?: string }).code === "23503") {
      return deny("该用户有草稿/历史数据，请改为「停用」");
    }
    return NextResponse.json({ success: false, error: "删除失败" }, { status: 500 });
  }
}
