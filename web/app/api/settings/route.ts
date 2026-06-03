import { NextResponse } from "next/server";
import { z } from "zod";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings, saveUserSettings, maskKey } from "@/lib/user-settings";
import { DEFAULT_GLOBAL_PROMPT } from "@/lib/prompts";
import { getActivePresetContent } from "@/lib/presets";

export const dynamic = "force-dynamic";

function buildResponse(
  s: Awaited<ReturnType<typeof getUserSettings>>,
  effectiveDefaultPrompt: string,
) {
  const deepseek = maskKey(s.deepseek_api_key); // 文案 = deepseek
  const qwen = maskKey(s.qwen_api_key); // 视频 = qwen
  // NOTE: raw API keys are intentionally NOT returned to the browser.
  // *_api_url / *_api_model are returned as-is (may be '') so the profile page
  // can show the runtime default as a placeholder when empty.
  return NextResponse.json({
    success: true,
    global_prompt: s.global_prompt || DEFAULT_GLOBAL_PROMPT,
    default_prompt: effectiveDefaultPrompt,
    // Backward-compatible flags (homepage gate uses these).
    hasDeepseekKey: deepseek.has,
    hasQwenKey: qwen.has,
    deepseekKeyMask: deepseek.mask,
    qwenKeyMask: qwen.mask,
    // Custom endpoints/models (raw, possibly empty).
    textApiUrl: s.text_api_url,
    textApiModel: s.text_api_model,
    videoApiUrl: s.video_api_url,
    videoApiModel: s.video_api_model,
  });
}

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return unauthorized();

  const [s, effectiveDefaultPrompt] = await Promise.all([
    getUserSettings(user.id),
    getActivePresetContent(user.id),
  ]);
  return buildResponse(s, effectiveDefaultPrompt);
}

const SaveSchema = z.object({
  deepseek_api_key: z.string().max(500).optional(),
  qwen_api_key: z.string().max(500).optional(),
  global_prompt: z.string().max(20_000).optional(),
  text_api_url: z.string().max(500).optional(),
  text_api_model: z.string().max(200).optional(),
  video_api_url: z.string().max(500).optional(),
  video_api_model: z.string().max(200).optional(),
  default_prompt: z.string().max(20_000).optional(),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: z.infer<typeof SaveSchema>;
  try {
    body = SaveSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ success: false, error: "请求格式不正确" }, { status: 400 });
  }

  // Blank/whitespace API keys mean "leave unchanged" (mapped to null).
  const blankToNull = (v: string | undefined) => (v && v.trim() ? v.trim() : null);
  // url/model/global_prompt: undefined = leave unchanged; any provided value
  // (including '') is written verbatim (allows clearing back to default).
  const passthrough = (v: string | undefined) => (v === undefined ? null : v.trim());
  await saveUserSettings(user.id, {
    deepseekKey: blankToNull(body.deepseek_api_key),
    qwenKey: blankToNull(body.qwen_api_key),
    globalPrompt: body.global_prompt === undefined ? null : body.global_prompt,
    textApiUrl: passthrough(body.text_api_url),
    textApiModel: passthrough(body.text_api_model),
    videoApiUrl: passthrough(body.video_api_url),
    videoApiModel: passthrough(body.video_api_model),
    defaultPrompt: body.default_prompt === undefined ? null : body.default_prompt,
  });

  const [s, effectiveDefaultPrompt] = await Promise.all([
    getUserSettings(user.id),
    getActivePresetContent(user.id),
  ]);
  return buildResponse(s, effectiveDefaultPrompt);
}
