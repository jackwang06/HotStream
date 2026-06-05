import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { getActiveSoulContent } from "@/lib/presets";
import { pythonBase } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 文案生成 API 运行时默认值（与 generate-copy 保持一致）
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";

// 图片分析 API 运行时默认值（与 analyze-video 保持一致）
const VIDEO_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const VIDEO_DEFAULT_MODEL = "qwen-vl-max";

// /api/ai-assist 现在是「流式」接口：Python 后端逐行写出 NDJSON 阶段事件
// （analyzing_images / image_failed / generating / done / error），本路由
// 注入凭据与灵魂后，把上游响应体「原样直通」返回浏览器，绝不缓冲，
// 这样编辑器才能用 resp.body.getReader() 实时驱动进度。
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
    // 缺 DeepSeek key：直接返回一条 error 事件（仍是 NDJSON 流的形状），
    // 这样前端流读取逻辑可以统一处理，不用区分「HTTP 错误」与「事件错误」。
    const line = JSON.stringify({
      phase: "error",
      success: false,
      error: "请在设置配置文案生成 API Key",
    });
    return new Response(line + "\n", {
      status: 200,
      headers: {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }

  // 注入 DeepSeek 凭据（文案生成）+ Qwen 凭据（rewrite 含图片时分析图片用）
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.deepseek_api_key,
    api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    model: settings.text_api_model || TEXT_DEFAULT_MODEL,
    qwen_api_key: settings.qwen_api_key || "",
    qwen_api_url: settings.video_api_url || VIDEO_DEFAULT_URL,
    qwen_model: settings.video_api_model || VIDEO_DEFAULT_MODEL,
  };

  // 注入当前代理灵魂作为 system 人设（global_prompt）
  const soul = await getActiveSoulContent(user.id);
  if (soul) payload.global_prompt = soul;

  // 直通流：不使用会缓冲整段响应的 proxyPostJson，而是把上游 resp.body 直接转发。
  try {
    const resp = await fetch(`${pythonBase()}/api/ai-assist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    return new Response(resp.body, {
      status: resp.status,
      headers: {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    const line = JSON.stringify({
      phase: "error",
      success: false,
      error: `后端服务不可用：${(e as Error).message}`,
    });
    return new Response(line + "\n", {
      status: 200,
      headers: {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }
}
