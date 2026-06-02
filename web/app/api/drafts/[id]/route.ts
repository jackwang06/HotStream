import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";

export const dynamic = "force-dynamic";

interface DraftRow {
  id: number;
  title: string;
  content_blocks: unknown;
  images: unknown;
  created_at: Date;
  updated_at: Date;
}

function parseId(idStr: string): number | null {
  const id = Number(idStr);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的草稿 ID" }, { status: 400 });

  const { rows } = await query<DraftRow>(
    `SELECT id, title, content_blocks, images, created_at, updated_at
       FROM drafts WHERE id = $1 AND user_id = $2`,
    [id, user.id],
  );
  if (!rows[0]) return NextResponse.json({ success: false, error: "草稿不存在" }, { status: 404 });
  return NextResponse.json({ success: true, draft: rows[0] });
}

const UpdateSchema = z.object({
  title: z.string().max(500).optional().default(""),
  content_blocks: z.array(z.any()).optional().default([]),
  images: z.array(z.any()).optional().default([]),
});

export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的草稿 ID" }, { status: 400 });

  let body: z.infer<typeof UpdateSchema>;
  try {
    body = UpdateSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  const { rows } = await query<DraftRow>(
    `UPDATE drafts SET title = $1, content_blocks = $2::jsonb, images = $3::jsonb, updated_at = now()
       WHERE id = $4 AND user_id = $5
       RETURNING id, title, content_blocks, images, created_at, updated_at`,
    [body.title, JSON.stringify(body.content_blocks), JSON.stringify(body.images), id, user.id],
  );
  if (!rows[0]) return NextResponse.json({ success: false, error: "草稿不存在" }, { status: 404 });
  return NextResponse.json({ success: true, draft: rows[0] });
}

export async function DELETE(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }
  const id = parseId((await params).id);
  if (!id) return NextResponse.json({ success: false, error: "无效的草稿 ID" }, { status: 400 });

  const { rowCount } = await query("DELETE FROM drafts WHERE id = $1 AND user_id = $2", [id, user.id]);
  if (!rowCount) return NextResponse.json({ success: false, error: "草稿不存在" }, { status: 404 });
  return NextResponse.json({ success: true });
}
