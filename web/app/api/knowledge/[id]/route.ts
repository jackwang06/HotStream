import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, forbidden, assertSameOrigin } from "@/lib/session";
import { getKnowledgeOwner, updateKnowledge, deleteKnowledge } from "@/lib/knowledge";

export const dynamic = "force-dynamic";

function parseId(idStr: string): number | null {
  const id = Number(idStr);
  return Number.isInteger(id) && id > 0 ? id : null;
}

const UpdateSchema = z.object({
  title: z.string().max(500),
  content: z.string().max(20000),
  tags: z.string().max(500).optional().default(""),
  enabled: z.boolean(),
});

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的条目 ID" }, { status: 400 });

  const owner = await getKnowledgeOwner(id);
  if (owner === undefined) {
    return NextResponse.json({ success: false, error: "条目不存在" }, { status: 404 });
  }
  // Only the creator or an admin may edit / enable-disable.
  if (user.role !== "admin" && owner !== user.id) return forbidden();

  let body: z.infer<typeof UpdateSchema>;
  try {
    body = UpdateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  const item = await updateKnowledge(id, {
    title: body.title,
    content: body.content,
    tags: body.tags,
    enabled: body.enabled,
  });
  if (!item) return NextResponse.json({ success: false, error: "条目不存在" }, { status: 404 });
  return NextResponse.json({ success: true, item });
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的条目 ID" }, { status: 400 });

  const owner = await getKnowledgeOwner(id);
  if (owner === undefined) {
    return NextResponse.json({ success: false, error: "条目不存在" }, { status: 404 });
  }
  // Only the creator or an admin may delete.
  if (user.role !== "admin" && owner !== user.id) return forbidden();

  const ok = await deleteKnowledge(id);
  if (!ok) return NextResponse.json({ success: false, error: "条目不存在" }, { status: 404 });
  return NextResponse.json({ success: true });
}
