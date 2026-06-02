import { NextResponse } from "next/server";
import { z } from "zod";
import { query } from "@/lib/db";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";

export const dynamic = "force-dynamic";

interface HistoryRow {
  id: number;
  topic_title: string;
  copy_text: string;
  hot_value: string;
  source: string;
  chars: number;
  created_at: Date;
}

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const { rows } = await query<HistoryRow>(
    `SELECT id, topic_title, copy_text, hot_value, source, chars, created_at
       FROM history WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50`,
    [user.id],
  );
  return NextResponse.json({ success: true, history: rows });
}

const RecordSchema = z.object({
  topic_title: z.string().max(2000).optional().default(""),
  copy_text: z.string().max(100_000).optional().default(""),
  hot_value: z.coerce.string().max(200).optional().default(""),
  source: z.string().max(200).optional().default(""),
  chars: z.coerce.number().int().min(0).optional().default(0),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof RecordSchema>;
  try {
    body = RecordSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  const { rows } = await query<{ id: number }>(
    `INSERT INTO history (user_id, topic_title, copy_text, hot_value, source, chars)
     VALUES ($1, $2, $3, $4, $5, $6) RETURNING id`,
    [user.id, body.topic_title, body.copy_text, body.hot_value, body.source, body.chars],
  );
  return NextResponse.json({ success: true, id: rows[0].id });
}
