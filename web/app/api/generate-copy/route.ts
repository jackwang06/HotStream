import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { getEnabledKnowledge } from "@/lib/knowledge";
import { getActivePresetContent } from "@/lib/presets";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 文案生成 API 运行时默认值（用户未自定义时使用）。OpenAI 兼容 /chat/completions。
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";

// 知识库注入上限（字符）。超出则截断并在末尾标注。
const KNOWLEDGE_MAX_CHARS = 8000;

// 取已启用的共享知识库条目，拼成单段文本供 AI 上下文使用；过长则截断。
async function buildKnowledgeText(): Promise<string> {
  const entries = await getEnabledKnowledge();
  if (!entries.length) return "";
  let text = entries.map((e) => `【${e.title}】\n${e.content}`).join("\n\n");
  if (text.length > KNOWLEDGE_MAX_CHARS) {
    text = text.slice(0, KNOWLEDGE_MAX_CHARS) + "\n\n（知识库内容过长已截断）";
  }
  return text;
}

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

  // Inject the user's key/url/model server-side; never trust client-supplied values.
  const payload: Record<string, unknown> = {
    ...body,
    api_key: settings.deepseek_api_key,
    api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    model: settings.text_api_model || TEXT_DEFAULT_MODEL,
  };
  // New model: the page sends default_prompt (the editable "本次提示词" template)
  // and the backend assembles topic materials around it. A legacy/foreign
  // temporary_prompt would be used verbatim by Python and bypass that assembly,
  // so strip it unconditionally to keep the contract single-pathed.
  delete payload.temporary_prompt;
  // Only forward global_prompt when the user has actually set one.
  if (settings.global_prompt) {
    payload.global_prompt = settings.global_prompt;
  }
  // Body (i.e., the page's "本次提示词") takes priority; fall back to the
  // user's effective default prompt (active preset → legacy column) only when
  // the request body didn't supply one.
  if (!payload.default_prompt) {
    const effective = await getActivePresetContent(user.id);
    if (effective) payload.default_prompt = effective;
  }
  // Inject the enabled shared knowledge-base entries (global, server-side).
  const knowledge = await buildKnowledgeText();
  if (knowledge) {
    payload.knowledge_base = knowledge;
  }

  const resp = await proxyPostJson("/api/generate-copy", payload, 70_000);
  if (!resp.ok) {
    const text = await resp.clone().text();
    if (/invalid_api_key|incorrect api key|authentication|401/i.test(text)) {
      return NextResponse.json(
        {
          success: false,
          error: "文案生成 API Key 无效或未授权。请到「设置」检查并重新填写文案生成 API Key。",
        },
        { status: 400 },
      );
    }
  }
  return resp;
}
