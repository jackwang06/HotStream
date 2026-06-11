from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hotstream.scenic_profile import scenic_profile_prompt_section

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
TEXT_DEFAULT_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def _normalize_chat_endpoint(api_url: str | None) -> str:
    """Resolve an OpenAI-compatible chat/completions endpoint from a base URL.

    Rule (must match the Next.js contract): if the URL already contains
    '/chat/completions' use it as-is; otherwise strip trailing slashes and
    append '/chat/completions'. Empty/None falls back to the text default URL.
    """
    base = (api_url or "").strip() or TEXT_DEFAULT_URL
    if "/chat/completions" in base:
        return base
    return base.rstrip("/") + "/chat/completions"

DEFAULT_GLOBAL_PROMPT = (
    "你是一名资深中文新媒体文案主笔，不是写作顾问。你的任务是直接输出一篇已经写好的推文正文，"
    "读者打开就能读，而不是告诉用户可以怎么写。必须基于用户提供的热点信息写作；"
    "禁止编造未提供的时间、地点、成绩、人物言论、采访内容、因果关系和具体数据。"
    "以热点标题和补充信息能确认的事实为边界；没有明确给出的内容，不要添加服装、动作、现场反应、赛果、采访原话等细节。"
    "如果事实信息不足，就围绕公众关注点、文化/情绪价值和传播意义展开，不要把推测写成事实。"
)

DEFAULT_USER_BRIEF = "适合小红书/公众号开头，语气简洁、有信息量，可直接发布。"

# 固定的 Markdown 排版指令：无论用户预设如何，都追加到 system_prompt，
# 保证 DeepSeek 输出是工整美观的 Markdown（供「预览即编辑器」WYSIWYG 解析为块）。
MARKDOWN_OUTPUT_INSTRUCTION = (
    "\n\n【输出格式 · 必须遵守】请用 Markdown 组织整篇正文，做到工整美观：\n"
    "- 用一行「# 」开头作为主标题（全篇只有一个 # 主标题）；\n"
    "- 用「## 」「### 」组织小标题，层级清晰；\n"
    "- 段落之间用一个空行分隔；\n"
    "- 重点词句用 **加粗**，需要强调时可用 *斜体*；\n"
    "- 不要用代码块（```）、表格、分割线（---）来包裹或承载正文；\n"
    "- 只输出推文正文本身，不要输出任何与正文无关的说明、解释或元信息。"
)

# 「政治脱敏」开启时追加到 system 提示的硬性约束。
POLITICAL_DESENSITIZE_INSTRUCTION = (
    "\n\n【政治脱敏 · 硬性要求】本次创作严禁涉及任何政治敏感内容——包括但不限于："
    "政党、政府、国家领导人与官员、政策法规、选举、外交、制裁、军事、国际冲突、"
    "意识形态、维权抗议、敏感地区的政治议题等。若热点本身带政治色彩，只从文旅、"
    "自然风光、民俗、美食、节庆、生活方式等**非政治**角度切入；无法剥离政治的内容"
    "一律回避不写。全文保持轻松正向的文旅营销风格，绝不出现上述任何政治元素。"
)

# 「默认提示词」= 每次生成文案的"任务+硬性要求+输出格式"指令脚手架。
# 这是与具体热点无关的指令模板，per-user 的 user_settings.default_prompt 为空时回落到它。
# 措辞与原 build_default_temporary_prompt 逐字保留，不要改写规则内容。
DEFAULT_PROMPT_TEMPLATE = (
    "请基于以下热点写一篇可直接发布的中文推文。\n\n"
    "硬性要求：\n"
    "1. 直接写成最终成稿，不要输出写作建议、选题建议、分析框架。\n"
    "2. 不要输出可选角度，不要使用“可以从三个角度”“建议从”等顾问式表达。\n"
    "3. 以热点标题、视频分析和景点画像能确认的事实为边界；没有明确给出的内容，不能当成已经发生的细节来写。\n"
    "4. 推文必须服务于前山牧场四季牧歌民俗风情园宣传，热点只作为切入点，不能写成泛热点评论。\n"
    "5. 如果热点来自 B站/抖音等视频，不能声称视频拍摄地就是前山牧场，除非源信息明确说明。\n"
    "6. 禁止编造价格、活动日期、营业时间、优惠政策、名人到访、交通班次、游客评价。\n"
    "7. 语气像真实公众号/小红书推文：有开头钩子、有信息展开、有情绪/观点、有结尾互动。\n"
    "8. 字数控制在 250-450 字，段落短，适合移动端阅读。\n\n"
    "输出格式（Markdown）：\n\n"
    "# 一句有传播感但不夸张的标题\n\n"
    "## 开头\n\n"
    "2-3 句，直接抓住读者注意力，可用 **加粗** 突出关键信息\n\n"
    "## 正文\n\n"
    "3-5 个短段落，围绕热点和前山牧场四季牧歌展开，不列提纲\n\n"
    "## 结尾\n\n"
    "一句互动式收束，引导评论或转发"
)


def load_project_env() -> None:
    """Load simple KEY=VALUE pairs from .env without adding a dependency."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _format_list_or_json(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _format_qwen_analysis(qwen_analysis: dict[str, Any] | None) -> str:
    if not qwen_analysis:
        return ""
    # 用户在前端编辑过的「视频内容推断」文本（或 DeepSeek 还原出的全貌）：逐字采用，
    # 确保 DeepSeek 文案生成收到的就是用户认可的版本。
    edited = str(qwen_analysis.get("edited_text") or qwen_analysis.get("inferred") or "").strip()
    if edited:
        return (
            "视频内容推断（综合封面+联网检索+模型还原，可能与真实视频有出入）：\n"
            + edited
            + "\n请把以上推断作为借势素材，紧扣其中内容写作，不要编造其中未提及的事实。"
        )
    lines = ["Qwen2.5-VL 视频分析："]
    for key, label in [
        ("summary", "内容概述"),
        ("scenes", "画面场景"),
        ("visual_keywords", "视觉关键词"),
        ("audience_emotion", "受众情绪"),
        ("usable_facts", "可使用事实"),
        ("risks", "风险提醒"),
    ]:
        formatted = _format_list_or_json(qwen_analysis.get(key))
        if formatted:
            lines.append(f"- {label}：{formatted}")
    lines.append("请只把视频分析作为借势素材，不要编造视频拍摄地或未确认事实。")
    return "\n".join(lines)


def build_default_temporary_prompt(
    topic: dict[str, Any],
    brief: str = "",
    qwen_analysis: dict[str, Any] | None = None,
    default_prompt: str | None = None,
) -> str:
    """Assemble the per-generation user prompt.

    Structure: instruction scaffold first (the static "task + hard rules +
    output format" template, which a user may override via ``default_prompt``),
    then the dynamic材料 block (this hot topic's title/source/heat, the Qwen
    video analysis, the scenic profile and the user's extra brief). The
    instruction scaffold is hot-topic agnostic; everything below the separator
    is auto-assembled from the current request.
    """
    title = str(topic.get("title", "")).strip()
    source = str(topic.get("source", "今日头条")).strip() or "今日头条"
    hot_value = topic.get("hot_value", "")
    label = str(topic.get("label", "")).strip()
    user_brief = brief.strip() or DEFAULT_USER_BRIEF

    topic_lines = [
        f"热点标题：{title}",
        f"来源：{source}",
    ]
    if hot_value not in (None, ""):
        topic_lines.append(f"热度：{hot_value}")
    if label:
        topic_lines.append(f"补充信息：{label}")
    if topic.get("url"):
        topic_lines.append(f"原始链接：{topic.get('url')}")
    if topic.get("desc"):
        topic_lines.append(f"视频/内容简介：{topic.get('desc')}")
    if topic.get("metrics"):
        topic_lines.append(f"公开流量数据：{json.dumps(topic.get('metrics'), ensure_ascii=False)}")
    qwen_section = _format_qwen_analysis(qwen_analysis)
    scenic_section = scenic_profile_prompt_section()

    instructions = (default_prompt or "").strip() or DEFAULT_PROMPT_TEMPLATE

    materials = (
        "\n".join(topic_lines)
        + ("\n\n" + qwen_section if qwen_section else "")
        + "\n\n景点画像与宣传约束：\n"
        + scenic_section
        + "\n\n用户补充要求："
        + user_brief
    )

    return (
        instructions
        + "\n\n——以下是本次热点信息与可用素材，请据此写作——\n\n"
        + materials
    )


def build_deepseek_messages(
    topic: dict[str, Any],
    brief: str = "",
    global_prompt: str | None = None,
    temporary_prompt: str | None = None,
    qwen_analysis: dict[str, Any] | None = None,
    knowledge_base: str | None = None,
    default_prompt: str | None = None,
    political_filter: bool = False,
) -> list[dict[str, str]]:
    system_prompt = (global_prompt or DEFAULT_GLOBAL_PROMPT).strip()
    # 无论用户预设如何，都追加固定的 Markdown 排版指令到 system_prompt，
    # 使输出统一为 Markdown（messages 结构不变，仍为 [system,(knowledge),user]）。
    system_prompt = system_prompt + MARKDOWN_OUTPUT_INSTRUCTION
    # 政治脱敏开启时，追加硬性涉政回避约束（叠加在所有用户预设之上）。
    if political_filter:
        system_prompt = system_prompt + POLITICAL_DESENSITIZE_INSTRUCTION
    user_prompt = (
        temporary_prompt
        or build_default_temporary_prompt(
            topic=topic,
            brief=brief,
            qwen_analysis=qwen_analysis,
            default_prompt=default_prompt,
        )
    ).strip()

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    knowledge_text = (knowledge_base or "").strip()
    if knowledge_text:
        messages.append({
            "role": "system",
            "content": (
                "以下是景区知识库参考资料（用户上传的景点/活动等信息）。"
                "生成推文时应优先据此宣传，并结合用户的本次要求；"
                "但严禁编造知识库与热点信息中未提供的事实：\n\n"
                + knowledge_text
            ),
        })
    messages.append({"role": "user", "content": user_prompt})
    return messages



# 「AI 帮写」三种操作的 user 提示词模板。expand/condense 目标固定、不考虑图片；
# rewrite 由用户给出具体要求，且可附带 Qwen 对所选图片的分析作为参考上下文。
AI_ASSIST_EXPAND_TEMPLATE = (
    "请在保持原意、立场与语言风格不变的前提下，扩写下面这段文案，"
    "使其更充实生动（仍是可直接发布的成稿，用 Markdown）：\n\n{text}"
)
AI_ASSIST_CONDENSE_TEMPLATE = (
    "请在保持原意与风格不变的前提下，精炼缩短下面这段文案（用 Markdown）：\n\n{text}"
)

# 「补充」(supplement) 模式：在光标处插入一段新内容，不改动已有正文。
# 与 expand/condense/rewrite 不同，supplement 不基于「选区」，而是基于
# 「光标前文 / 光标后文」上下文，按用户要求生成一段可直接插入的文案。
AI_ASSIST_SUPPLEMENT_TEMPLATE = (
    "请在不改动已有内容的前提下，按以下要求补充一段可直接插入到光标处的文案"
    "（与上下文风格一致，用 Markdown，只输出要补充的内容本身，不要重复已有内容）。\n"
    "要求：{requirement}\n\n"
    "【光标前文】\n{before_text}\n\n"
    "【光标后文】\n{after_text}"
)


def build_ai_assist_messages(
    mode: str,
    selected_text: str = "",
    requirement: str = "",
    global_prompt: str | None = None,
    image_analysis: str = "",
    before_text: str = "",
    after_text: str = "",
    political_filter: bool = False,
) -> list[dict[str, str]]:
    """Assemble the [system, user] messages for the 「AI 帮写」 (AI assist) feature.

    system = active soul (or default) + the fixed Markdown output instruction, so
    the rewritten/expanded/condensed text keeps the agent's persona and stays in
    Markdown for round-tripping into the WYSIWYG editor. The user message depends
    on ``mode``:

    - ``expand``   : enrich the selection while preserving meaning/stance/style.
    - ``condense`` : tighten/shorten the selection while preserving meaning/style.
    - ``rewrite``  : rewrite per the user's ``requirement``; if ``image_analysis``
      is supplied (Qwen's read of the images inside the selection) it is appended
      as reference-only context.
    - ``supplement``: generate a new passage to insert at the caret per the user's
      ``requirement``, using ``before_text``/``after_text`` as surrounding context
      (no selection involved, no images).
    """
    system_prompt = (global_prompt or DEFAULT_GLOBAL_PROMPT).strip() + MARKDOWN_OUTPUT_INSTRUCTION
    # 政治脱敏开启时，AI帮写(扩写/缩写/改写/补充)同样注入涉政回避硬约束。
    if political_filter:
        system_prompt = system_prompt + POLITICAL_DESENSITIZE_INSTRUCTION
    text = (selected_text or "").strip()
    normalized_mode = (mode or "").strip().lower()

    if normalized_mode == "expand":
        user_prompt = AI_ASSIST_EXPAND_TEMPLATE.format(text=text)
    elif normalized_mode == "condense":
        user_prompt = AI_ASSIST_CONDENSE_TEMPLATE.format(text=text)
    elif normalized_mode == "supplement":
        user_prompt = AI_ASSIST_SUPPLEMENT_TEMPLATE.format(
            requirement=(requirement or "").strip(),
            before_text=(before_text or "").strip(),
            after_text=(after_text or "").strip(),
        )
    elif normalized_mode == "rewrite":
        reference = (image_analysis or "").strip()
        reference_block = (
            (
                "\n参考图片分析（仅作参考，不要编造图中没有的事实）：\n" + reference
            )
            if reference
            else ""
        )
        user_prompt = (
            "请按以下要求改写下面这段文案（保持与全文一致的语言风格，用 Markdown）。\n"
            f"要求：{(requirement or '').strip()}"
            f"{reference_block}\n\n"
            f"原文案：\n{text}"
        )
    else:
        raise ValueError(f"未知的 AI 帮写操作：{mode!r}")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_ai_assist(
    mode: str,
    selected_text: str = "",
    requirement: str = "",
    global_prompt: str | None = None,
    image_analysis: str = "",
    before_text: str = "",
    after_text: str = "",
    api_key: str | None = None,
    model: str | None = None,
    api_url: str | None = None,
    timeout: int = 45,
    political_filter: bool = False,
) -> str:
    """Run the 「AI 帮写」 expand/condense/rewrite/supplement operation via DeepSeek.

    Returns the rewritten copy as plain text (Markdown). Reuses the same
    endpoint normalization / DeepSeek request shape / content extraction as
    :func:`generate_copy_with_deepseek` so the contract stays single-pathed.

    ``supplement`` does not act on a selection — it produces a new passage to
    insert at the caret, driven by ``requirement`` plus the surrounding
    ``before_text`` / ``after_text`` context (no images).
    """
    load_project_env()
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("DeepSeek API Key 未填写")

    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "supplement":
        if not (requirement or "").strip():
            raise RuntimeError("请填写补充的具体要求")
    elif not (selected_text or "").strip():
        raise RuntimeError("没有选中可供改写的文案")

    messages = build_ai_assist_messages(
        mode=mode,
        selected_text=selected_text,
        requirement=requirement,
        global_prompt=global_prompt,
        image_analysis=image_analysis,
        before_text=before_text,
        after_text=after_text,
        political_filter=political_filter,
    )

    endpoint = _normalize_chat_endpoint(api_url)
    resolved_model = (model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": messages,
        "temperature": 0.72,
        "max_tokens": 1200,
        "stream": False,
    }
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return _extract_deepseek_content(payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek 调用失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek 网络请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无法解析的 JSON") from exc


# 精选热点（curated topics）允许选出的上限。提示词与解析层都以此为界。
CURATED_TOPICS_MAX = 12


def _extract_selection_object(text: str) -> dict[str, Any] | None:
    """Best-effort parse of the DeepSeek selection reply into a JSON object.

    Mirrors ``video_analyzer._extract_json_object``: try the raw text, any
    ```json fenced block, then the outermost ``{...}`` span via regex, returning
    the first candidate that decodes to a dict. Returns ``None`` if none parse.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.S | re.I)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    obj = re.search(r"\{.*\}", stripped, re.S)
    if obj:
        candidates.append(obj.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _build_selection_messages(
    topics: list[dict[str, Any]],
    knowledge_base: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the [system, user] messages asking DeepSeek to pick borrowable hot topics.

    The user message stacks: the scenic profile (so the model knows what the
    venue is and what it can credibly借势), the optional knowledge-base
    reference (planned activities etc.), the numbered topic list (one per line as
    ``序号. [来源] 标题``) and the selection instruction with the strict JSON
    output contract.
    """
    system_prompt = (
        "你是文旅借势选品助手，为「前山牧场四季牧歌民俗风情园」"
        "从一批全网热点里挑出最适合借势宣传的。只依据给定信息判断。"
    )

    sections: list[str] = [scenic_profile_prompt_section()]

    knowledge_text = (knowledge_base or "").strip()
    if knowledge_text:
        sections.append("知识库参考资料（景区已上传的景点/活动等信息）：\n" + knowledge_text)

    topic_lines = []
    for index, topic in enumerate(topics, start=1):
        source = str(topic.get("source") or "").strip() or "未知来源"
        title = str(topic.get("title") or "").strip()
        topic_lines.append(f"{index}. [{source}] {title}")
    sections.append("候选热点清单（每行：序号. [来源] 标题）：\n" + "\n".join(topic_lines))

    sections.append(
        f"请从以上候选中选出最多 {CURATED_TOPICS_MAX} 条最适合为本景点借势宣传的热点"
        "（风光/旅游/乡村/文旅类，或与知识库中将办活动相关的热点）。"
        "严格只返回 JSON 对象，格式为 {\"selected\":[{\"index\":序号, \"reason\":\"20字内理由\"}]}，"
        "index 必须是上面清单里的序号整数。"
        "宁缺毋滥：不要选与景点无关、只能硬蹭的热点；没有合适的就返回空数组。"
        "除 JSON 外不要输出任何其它文字。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(sections)},
    ]


def select_relevant_topics(
    topics: list[dict[str, Any]],
    knowledge_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    api_url: str | None = None,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """Use DeepSeek to curate the borrow-worthy hot topics for the venue.

    Aggregates a numbered list of candidate topics (each carrying its original
    ``source``) plus the scenic profile and the enabled knowledge base, then asks
    DeepSeek to return ``{"selected":[{"index":..,"reason":..}]}``. The reply is
    parsed robustly (markdown fences stripped, outermost ``{...}`` span matched);
    each returned index maps back to the original topic, which is returned with an
    added ``reason`` field and its source preserved. Returns ``[]`` on empty
    input, a parse failure, or an empty selection — never raises for those cases
    (only an unfilled API key / network error propagates).
    """
    if not topics:
        return []
    load_project_env()
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("DeepSeek API Key 未填写")

    endpoint = _normalize_chat_endpoint(api_url)
    resolved_model = (model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": _build_selection_messages(topics, knowledge_base=knowledge_base),
        "temperature": 0.3,
        "max_tokens": 1200,
        "stream": False,
    }
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = _extract_deepseek_content(payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek 调用失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek 网络请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无法解析的 JSON") from exc

    parsed = _extract_selection_object(content)
    if not parsed:
        return []
    selected = parsed.get("selected")
    if not isinstance(selected, list):
        return []

    results: list[dict[str, Any]] = []
    seen_indices: set[int] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        raw_index = item.get("index")
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        # 1-based index into the original topics list; skip out-of-range/dupes.
        if index < 1 or index > len(topics) or index in seen_indices:
            continue
        seen_indices.add(index)
        topic = dict(topics[index - 1])
        reason = str(item.get("reason") or "").strip()
        if reason:
            topic["reason"] = reason
        results.append(topic)
        if len(results) >= CURATED_TOPICS_MAX:
            break
    return results


def _build_video_restore_messages(
    title: str,
    source: str,
    overview: str,
    snippets: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """构造"还原视频/热点全貌"的 DeepSeek messages：概况 + 网络碎片 → 推断全貌。"""
    snippet_lines: list[str] = []
    for i, snip in enumerate(snippets or [], start=1):
        line = f"{i}. [{str(snip.get('source') or '')}] {str(snip.get('title') or '').strip()}"
        abstract = str(snip.get("abstract") or "").strip()
        if abstract:
            line += f" —— {abstract}"
        snippet_lines.append(line)
    snippets_block = "\n".join(snippet_lines) if snippet_lines else "（未检索到额外网络信息）"
    system = (
        "你是严谨的内容还原助手。基于给定的视频/热点概况，以及从网络检索到的零散信息，"
        "并结合你已有的知识，推断并还原这个视频/热点最可能在讲什么。"
        "务必明确这是【推断】而非确证；信息不足处不要硬编细节、可如实说明不确定。"
        "输出 150–300 字中文：先一句话主旨，再分点列可借势的要点与情绪基调。"
    )
    user = (
        f"标题：{title}\n来源：{source or '未知'}\n\n"
        f"封面/标题/简介概况：\n{(overview or '（无）').strip()}\n\n"
        f"网络检索到的相关信息：\n{snippets_block}\n\n"
        "请据此还原这个视频/热点最可能的完整内容（标注为推断）。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def restore_topic_full_picture(
    title: str,
    source: str,
    overview: str,
    snippets: list[dict[str, Any]],
    api_key: str | None = None,
    model: str | None = None,
    api_url: str | None = None,
    timeout: int = 60,
) -> str:
    """让 DeepSeek 综合"概况 + 网络碎片 + 自身知识"还原热点全貌，返回纯文本（推断）。

    未填 Key 时抛错；网络/HTTP/解析错误也抛错（由调用方决定是否降级）。
    """
    load_project_env()
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("DeepSeek API Key 未填写")
    endpoint = _normalize_chat_endpoint(api_url)
    resolved_model = (model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": _build_video_restore_messages(title, source, overview, snippets),
        "temperature": 0.5,
        "max_tokens": 600,
        "stream": False,
    }
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _extract_deepseek_content(payload).strip()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek 调用失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek 网络请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无法解析的 JSON") from exc


def _extract_deepseek_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek 未返回可用文案")
    message = choices[0].get("message") or {}
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("DeepSeek 返回内容为空")
    return content


def generate_copy_with_deepseek(
    topic: dict[str, Any],
    brief: str = "",
    api_key: str | None = None,
    model: str | None = None,
    timeout: int = 45,
    global_prompt: str | None = None,
    temporary_prompt: str | None = None,
    qwen_analysis: dict[str, Any] | None = None,
    api_url: str | None = None,
    knowledge_base: str | None = None,
    default_prompt: str | None = None,
    political_filter: bool = False,
) -> str:
    """Generate copy for a selected hot topic using DeepSeek chat completions."""
    load_project_env()
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("DeepSeek API Key 未填写")

    endpoint = _normalize_chat_endpoint(api_url)
    resolved_model = (model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": build_deepseek_messages(
            topic=topic,
            brief=brief,
            global_prompt=global_prompt,
            temporary_prompt=temporary_prompt,
            qwen_analysis=qwen_analysis,
            knowledge_base=knowledge_base,
            default_prompt=default_prompt,
            political_filter=political_filter,
        ),
        "temperature": 0.72,
        "max_tokens": 1200,
        "stream": False,
    }
    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return _extract_deepseek_content(payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek 调用失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek 网络请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无法解析的 JSON") from exc
