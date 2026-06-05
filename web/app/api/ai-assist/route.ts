import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { getActiveSoulContent } from "@/lib/presets";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 文案生成 API 运行时默认值（与 generate-copy 保持一致）
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";

// 图片分析 API 运行时默认值（与 analyze-video 保持一致）
const VIDEO_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const VIDEO_DEFAULT_MODEL = "qwen-vl-max";

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }

  const settings = await getUserSettings(user.id);
  if (!settings.deepseek_api_key) {
    return NextResponse.json(
      { success: false, error: "请在设置配置文案生成 API Key" },
      { status: 400 },
    );
  }

  // 注入 DeepSeek 凭据（文案改写）
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.deepseek_api_key,
    api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    model: settings.text_api_model || TEXT_DEFAULT_MODEL,
  };

  // 注入 Qwen 凭据（rewrite 模式含图片时分析图片用）
  payload.qwen_api_key = settings.qwen_api_key || "";
  payload.qwen_api_url = settings.video_api_url || VIDEO_DEFAULT_URL;
  payload.qwen_model = settings.video_api_model || VIDEO_DEFAULT_MODEL;

  // 注入当前代理灵魂作为 system 人设（global_prompt）
  const soul = await getActiveSoulContent(user.id);
  if (soul) payload.global_prompt = soul;

  const resp = await proxyPostJson("/api/ai-assist", payload, 70_000);
  if (!resp.ok) {
    const text = await resp.clone().text();
    if (/invalid_api_key|incorrect api key|authentication|401/i.test(text)) {
      return NextResponse.json(
        {
          success: false,
          error:
            "文案生成 API Key 无效或未授权。请到「设置」检查并重新填写文案生成 API Key。",
        },
        { status: 400 },
      );
    }
  }
  return resp;
}
