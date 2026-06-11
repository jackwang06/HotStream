import { NextResponse } from "next/server";
import { getCurrentUser, unauthorized, assertSameOrigin } from "@/lib/session";
import { getUserSettings } from "@/lib/user-settings";
import { getEnabledKnowledge } from "@/lib/knowledge";
import { proxyPostJson } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// 文案生成 API 运行时默认值（用户未自定义时使用）。OpenAI 兼容 /chat/completions。
const TEXT_DEFAULT_URL = "https://api.deepseek.com";
const TEXT_DEFAULT_MODEL = "deepseek-chat";

// 知识库注入上限（字符）。超出则截断并在末尾标注。与 generate-copy 同款逻辑。
const KNOWLEDGE_MAX_CHARS = 8000;

// 取已启用的共享知识库条目，拼成单段文本供 AI 精选时参考；过长则截断。
async function buildKnowledgeText(): Promise<string> {
  const entries = await getEnabledKnowledge();
  if (!entries.length) return "";
  let text = entries.map((e) => `【${e.title}】\n${e.content}`).join("\n\n");
  if (text.length > KNOWLEDGE_MAX_CHARS) {
    text = text.slice(0, KNOWLEDGE_MAX_CHARS) + "\n\n（知识库内容过长已截断）";
  }
  return text;
}

// POST /api/curated-topics — 「精选热点」。聚合全网热点后由 DeepSeek 结合
// 景点画像 + 知识库精选出最契合本景点借势宣传的热点。凭证服务端注入。
export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return unauthorized();
  if (!assertSameOrigin(req)) {
    return NextResponse.json({ success: false, error: "跨站请求被拒绝" }, { status: 403 });
  }

  const settings = await getUserSettings(user.id);
  if (!settings.deepseek_api_key) {
    return NextResponse.json(
      { success: false, error: "请在设置配置文案生成 API Key" },
      { status: 400 },
    );
  }

  // 读取客户端 body 仅为取「政治脱敏」开关（其余凭证一律服务端注入，不信客户端）。
  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }

  // Inject the user's key/url/model server-side; never trust client-supplied
  // values. The aggregation + curation runs entirely in the Python backend.
  const payload: Record<string, unknown> = {
    api_key: settings.deepseek_api_key,
    api_url: settings.text_api_url || TEXT_DEFAULT_URL,
    model: settings.text_api_model || TEXT_DEFAULT_MODEL,
  };
  // 政治脱敏开关：转发给 Python，聚合后剔除涉政热点。
  if (body.political_filter) payload.political_filter = true;
  // Inject the enabled shared knowledge-base entries (global, server-side) so the
  // model can prefer hot topics that match planned activities etc.
  const knowledge = await buildKnowledgeText();
  if (knowledge) {
    payload.knowledge_base = knowledge;
  }

  // Aggregating 5 sources + a DeepSeek selection call takes longer than a single
  // generation, so allow a generous timeout.
  const resp = await proxyPostJson("/api/curated-topics", payload, 90_000);
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
