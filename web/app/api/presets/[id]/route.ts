import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, forbidden, assertSameOrigin } from "@/lib/session";
import { getPresetOwner, updatePreset, deletePreset, setActivePreset } from "@/lib/presets";

export const dynamic = "force-dynamic";

function parseId(idStr: string): number | null {
  const id = Number(idStr);
  return Number.isInteger(id) && id > 0 ? id : null;
}

const UpdateSchema = z.object({
  name: z.string().trim().min(1).max(200).optional(),
  content: z.string().max(20_000).optional(),
  active: z.boolean().optional(),
});

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的预设 ID" }, { status: 400 });

  const owner = await getPresetOwner(id);
  if (owner === undefined) {
    return NextResponse.json({ success: false, error: "预设不存在" }, { status: 404 });
  }
  if (user.role !== "admin" && owner !== user.id) return forbidden();

  let body: z.infer<typeof UpdateSchema>;
  try {
    body = UpdateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  // Update name/content if provided. For admin acting on another user's preset,
  // updatePreset uses the owner's userId so the WHERE clause matches.
  if (body.name !== undefined || body.content !== undefined) {
    const targetUserId = (owner ?? user.id) as number;
    await updatePreset(targetUserId, id, { name: body.name, content: body.content });
  }

  // Set as active for the preset owner when active === true.
  if (body.active === true) {
    const targetUserId = (owner ?? user.id) as number;
    await setActivePreset(targetUserId, id);
  }

  return NextResponse.json({ success: true });
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的预设 ID" }, { status: 400 });

  const owner = await getPresetOwner(id);
  if (owner === undefined) {
    return NextResponse.json({ success: false, error: "预设不存在" }, { status: 404 });
  }
  if (user.role !== "admin" && owner !== user.id) return forbidden();

  // deletePreset clears active_preset_id via FK ON DELETE SET NULL.
  const targetUserId = (owner ?? user.id) as number;
  const ok = await deletePreset(targetUserId, id);
  if (!ok) return NextResponse.json({ success: false, error: "预设不存在" }, { status: 404 });

  return NextResponse.json({ success: true });
}
