import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { listPresets, createPreset, setActivePreset } from "@/lib/presets";

export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const { presets, activePresetId } = await listPresets(user.id);
  return NextResponse.json({ success: true, presets, activePresetId });
}

const CreateSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "名称不能为空")
    .max(200),
  content: z.string().max(20_000).optional().default(""),
});

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
    return NextResponse.json({ success: false, error: "请求格式不正确（名称必填）" }, { status: 400 });
  }

  const preset = await createPreset(user.id, body.name, body.content);

  // If this is the user's first preset, auto-set it as active.
  const { presets } = await listPresets(user.id);
  if (presets.length === 1) {
    await setActivePreset(user.id, preset.id);
  }

  return NextResponse.json({ success: true, preset });
}
