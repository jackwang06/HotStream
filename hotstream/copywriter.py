from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

DEFAULT_GLOBAL_PROMPT = (
    "你是一名资深中文新媒体文案主笔，不是写作顾问。你的任务是直接输出一篇已经写好的推文正文，"
    "读者打开就能读，而不是告诉用户可以怎么写。必须基于用户提供的热点信息写作；"
    "禁止编造未提供的时间、地点、成绩、人物言论、采访内容、因果关系和具体数据。"
    "以热点标题和补充信息能确认的事实为边界；没有明确给出的内容，不要添加服装、动作、现场反应、赛果、采访原话等细节。"
    "如果事实信息不足，就围绕公众关注点、文化/情绪价值和传播意义展开，不要把推测写成事实。"
)

DEFAULT_USER_BRIEF = "适合小红书/公众号开头，语气简洁、有信息量，可直接发布。"


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


def build_default_temporary_prompt(topic: dict[str, Any], brief: str = "") -> str:
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

    return (
        "请基于以下热点写一篇可直接发布的中文推文。\n\n"
        + "\n".join(topic_lines)
        + "\n\n用户补充要求："
        + user_brief
        + "\n\n硬性要求：\n"
        + "1. 直接写成最终成稿，不要输出写作建议、选题建议、分析框架。\n"
        + "2. 不要输出可选角度，不要使用“可以从三个角度”“建议从”等顾问式表达。\n"
        + "3. 以热点标题和补充信息能确认的事实为边界；热点标题没有说明的事实，不能当成已经发生的细节来写。\n"
        + "4. 语气像真实公众号/小红书推文：有开头钩子、有信息展开、有情绪/观点、有结尾互动。\n"
        + "5. 字数控制在 250-450 字，段落短，适合移动端阅读。\n\n"
        + "输出格式：\n"
        + "标题：一句有传播感但不夸张的标题\n\n"
        + "开头：2-3 句，直接抓住读者注意力\n\n"
        + "正文：3-5 个短段落，围绕热点本身展开，不列提纲\n\n"
        + "结尾：一句互动式收束，引导评论或转发"
    )


def build_deepseek_messages(
    topic: dict[str, Any],
    brief: str = "",
    global_prompt: str | None = None,
    temporary_prompt: str | None = None,
) -> list[dict[str, str]]:
    system_prompt = (global_prompt or DEFAULT_GLOBAL_PROMPT).strip()
    user_prompt = (temporary_prompt or build_default_temporary_prompt(topic=topic, brief=brief)).strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]



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
) -> str:
    """Generate copy for a selected hot topic using DeepSeek chat completions."""
    load_project_env()
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("DeepSeek API Key 未填写")

    resolved_model = (model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": build_deepseek_messages(
            topic=topic,
            brief=brief,
            global_prompt=global_prompt,
            temporary_prompt=temporary_prompt,
        ),
        "temperature": 0.72,
        "max_tokens": 1200,
        "stream": False,
    }
    request = Request(
        DEEPSEEK_API_URL,
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
