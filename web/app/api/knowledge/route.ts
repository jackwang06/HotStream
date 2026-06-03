import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { listKnowledge, createKnowledge } from "@/lib/knowledge";

export const dynamic = "force-dynamic";

// GET — all shared entries (any logged-in user). canEdit is computed per row.
export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const items = await listKnowledge(user.id, user.role === "admin");
  return NextResponse.json({ success: true, items });
}

const CreateSchema = z.object({
  title: z.string().max(500),
  content: z.string().max(20000),
  tags: z.string().max(500).optional().default(""),
});

// POST — any logged-in user may add an entry; created_by = current user.
export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof CreateSchema>;
  try {
    body = CreateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }
  if (!body.title.trim() && !body.content.trim()) {
    return NextResponse.json({ success: false, error: "标题和内容不能同时为空" }, { status: 400 });
  }

  const item = await createKnowledge(user.id, {
    title: body.title,
    content: body.content,
    tags: body.tags,
  });
  return NextResponse.json({ success: true, item });
}
