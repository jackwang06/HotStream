import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 文案生成 API 运行时默认值（用户未自定义时使用）。OpenAI 兼容 /chat/completions。
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
  if (!settings.deepseek_api_key) {
    return NextResponse.json(
      { success: false, error: "请在用户信息配置文案生成 API Key" },
      { status: 400 },
    );
  }

  // Inject the user's key/url/model server-side; never trust client-supplied values.
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.deepseek_api_key,
    api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    model: settings.text_api_model || TEXT_DEFAULT_MODEL,
  };
  // Only forward global_prompt when the user has actually set one.
  if (settings.global_prompt) {
    payload.global_prompt = settings.global_prompt;
  }

  const resp = await proxyPostJson("/api/generate-copy", payload, 70_000);
  if (!resp.ok) {
    const text = await resp.clone().text();
    if (/invalid_api_key|incorrect api key|authentication|401/i.test(text)) {
      return NextResponse.json(
        {
          success: false,
          error: "文案生成 API Key 无效或未授权。请到「用户信息」检查并重新填写文案生成 API Key。",
        },
        { status: 400 },
      );
    }
  }
  return resp;
}
