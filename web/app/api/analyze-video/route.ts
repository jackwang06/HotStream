import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 视频分析 API 运行时默认值（用户未自定义时使用）。OpenAI 兼容 /chat/completions。
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
  if (!settings.qwen_api_key) {
    return NextResponse.json(
      { success: false, error: "请在用户信息配置视频分析 API Key" },
      { status: 400 },
    );
  }

  // Inject the user's key/url/model server-side; never trust client-supplied values.
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.qwen_api_key,
    api_url: settings.video_api_url || VIDEO_DEFAULT_URL,
    model: settings.video_api_model || VIDEO_DEFAULT_MODEL,
  };

  const resp = await proxyPostJson("/api/analyze-video", payload, 90_000);
  if (!resp.ok) {
    const text = await resp.clone().text();
    if (/invalid_api_key|incorrect api key|invalid[\s_-]?token|401/i.test(text)) {
      return NextResponse.json(
        {
          success: false,
          error:
            "视频分析 API Key 无效或未授权。请到「用户信息」填写视频分析 API Key —— 它与文案生成的 Key 不同，不能混用。",
        },
        { status: 400 },
      );
    }
  }
  return resp;
}
