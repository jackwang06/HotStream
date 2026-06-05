import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { listPresets, createPreset, setActivePreset, type PresetKind } from "@/lib/presets";

export const dynamic = "force-dynamic";

// Resolve the requested kind from the ?kind= query (defaults to 'default').
function kindFromSearch(url: string): PresetKind {
  const k = new URL(url).searchParams.get("kind");
  return k === "soul" ? "soul" : "default";
}

export async function GET(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const kind = kindFromSearch(req.url);
  const { presets, activePresetId, activeSoulPresetId } = await listPresets(user.id, kind);
  return NextResponse.json({ success: true, presets, activePresetId, activeSoulPresetId });
}

const CreateSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "名称不能为空")
    .max(200),
  content: z.string().max(20_000).optional().default(""),
  // Body may override ?kind; falls back to the query param, then 'default'.
  kind: z.enum(["default", "soul"]).optional(),
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

  const kind: PresetKind = body.kind ?? kindFromSearch(req.url);
  const preset = await createPreset(user.id, body.name, body.content, kind);

  // If this is the user's first preset of this kind, auto-set it as active.
  const { presets } = await listPresets(user.id, kind);
  if (presets.length === 1) {
    await setActivePreset(user.id, preset.id);
  }

  return NextResponse.json({ success: true, preset });
}
