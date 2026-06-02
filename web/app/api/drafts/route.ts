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

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const { rows } = await query<DraftRow>(
    `SELECT id, title, content_blocks, images, created_at, updated_at
       FROM drafts WHERE user_id = $1 ORDER BY updated_at DESC`,
    [user.id],
  );
  return NextResponse.json({ success: true, drafts: rows });
}

const DraftSchema = z.object({
  title: z.string().max(500).optional().default(""),
  content_blocks: z.array(z.any()).optional().default([]),
  images: z.array(z.any()).optional().default([]),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof DraftSchema>;
  try {
    body = DraftSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  const { rows } = await query<DraftRow>(
    `INSERT INTO drafts (user_id, title, content_blocks, images)
     VALUES ($1, $2, $3::jsonb, $4::jsonb)
     RETURNING id, title, content_blocks, images, created_at, updated_at`,
    [user.id, body.title, JSON.stringify(body.content_blocks), JSON.stringify(body.images)],
  );
  return NextResponse.json({ success: true, draft: rows[0] });
}
