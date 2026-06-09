import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 视频分析 API 运行时默认值（用户未自定义时使用）。OpenAI 兼容 /chat/completions。
const VIDEO_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const VIDEO_DEFAULT_MODEL = "qwen-vl-max";
// DeepSeek 用于「联网检索后还原视频全貌」这一步（OpenAI 兼容 /chat/completions）。
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";

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
  if (!settings.qwen_api_key) {
    return NextResponse.json(
      { success: false, error: "请在设置配置视频分析 API Key" },
      { status: 400 },
    );
  }

  // Inject the user's key/url/model server-side; never trust client-supplied values.
  // Qwen 做封面概况；DeepSeek（若已配置）做「联网检索→还原全貌」，未配置则后端降级。
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.qwen_api_key,
    api_url: settings.video_api_url || VIDEO_DEFAULT_URL,
    model: settings.video_api_model || VIDEO_DEFAULT_MODEL,
    deepseek_api_key: settings.deepseek_api_key || "",
    deepseek_api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    deepseek_model: settings.text_api_model || TEXT_DEFAULT_MODEL,
  };

  // 管线为 Qwen + 并发联网检索(≈6s) + DeepSeek 还原(≤30s)；给足余量，确保慢速时仍走
  // Python 端的 200 降级，而不是代理先 AbortError 返回 502。
  const resp = await proxyPostJson("/api/analyze-video", payload, 150_000);
  if (!resp.ok) {
    const text = await resp.clone().text();
    if (/invalid_api_key|incorrect api key|invalid[\s_-]?token|401/i.test(text)) {
      return NextResponse.json(
        {
          success: false,
          error:
            "视频分析 API Key 无效或未授权。请到「设置」填写视频分析 API Key —— 它与文案生成的 Key 不同，不能混用。",
        },
        { status: 400 },
      );
    }
  }
  return resp;
}
