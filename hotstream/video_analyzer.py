from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_QWEN_MODEL = "qwen2.5-vl-7b-instruct"


def _normalize_image_url(url: Any) -> str:
    text = str(url or "").strip()
    if text.startswith("//"):
        return "https:" + text
    return text


def build_video_materials(topic: dict[str, Any]) -> list[dict[str, str]]:
    """Return best-effort video visual materials for the editor.

    MVP uses the Bilibili cover because full video frame extraction needs signed
    play URLs and ffmpeg. The shape matches the existing editor material schema.
    """
    cover = _normalize_image_url(topic.get("cover") or topic.get("pic") or topic.get("thumbnail"))
    if not cover:
        return []
    title = str(topic.get("title") or "视频").strip() or "视频"
    return [{
        "url": cover,
        "thumbnail": cover,
        "title": f"B站视频封面：{title}",
        "source": "B站封面",
    }]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
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


def _normalize_analysis(raw_text: str) -> dict[str, Any]:
    parsed = _extract_json_object(raw_text)
    if not parsed:
        return {
            "summary": raw_text.strip(),
            "scenes": [],
            "visual_keywords": [],
            "audience_emotion": [],
            "usable_facts": [],
            "risks": ["模型未返回结构化 JSON，生成推文时必须严格避免编造未确认事实。"],
        }
    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "scenes": list(parsed.get("scenes") or []),
        "visual_keywords": list(parsed.get("visual_keywords") or []),
        "audience_emotion": list(parsed.get("audience_emotion") or []),
        "usable_facts": list(parsed.get("usable_facts") or []),
        "risks": list(parsed.get("risks") or []),
    }


def _extract_qwen_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Qwen 未返回可用视频分析")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                text_parts.append(str(part.get("text") or ""))
            else:
                text_parts.append(str(part))
        content = "\n".join(text_parts)
    text = str(content or "").strip()
    if not text:
        raise RuntimeError("Qwen 返回内容为空")
    return text


def _build_qwen_messages(topic: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(topic.get("title") or "").strip()
    url = str(topic.get("url") or "").strip()
    desc = str(topic.get("desc") or topic.get("description") or topic.get("label") or "").strip()
    metrics = topic.get("metrics") or topic.get("stats") or {}
    cover = _normalize_image_url(topic.get("cover") or topic.get("pic") or topic.get("thumbnail"))
    user_content: list[dict[str, Any]] = []
    if cover:
        user_content.append({"type": "image_url", "image_url": {"url": cover}})
    user_content.append({
        "type": "text",
        "text": (
            "请分析这个 B站热门视频，并输出严格 JSON，字段必须包括："
            "summary、scenes、visual_keywords、audience_emotion、usable_facts、risks。\n"
            "品牌目标：为「前山牧场四季牧歌民俗风情园」生成借势推广推文提供素材。\n"
            "只基于输入的封面/标题/简介/公开流量数据分析，不要编造视频里没有的事实；"
            "尤其不要声称该视频拍摄地就是前山牧场，除非输入明确说明。\n\n"
            f"视频标题：{title}\n"
            f"视频链接：{url}\n"
            f"视频简介：{desc}\n"
            f"流量数据：{json.dumps(metrics, ensure_ascii=False)}"
        ),
    })
    return [
        {"role": "system", "content": [{"type": "text", "text": "你是谨慎的视频内容分析助手，只输出可用于文旅借势营销的结构化事实与风险。"}]},
        {"role": "user", "content": user_content},
    ]


def analyze_video_with_qwen(
    topic: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    resolved_api_key = (api_key or "").strip()
    if not resolved_api_key:
        raise RuntimeError("Qwen API Key 未填写")
    resolved_model = (model or DEFAULT_QWEN_MODEL).strip()
    body = {
        "model": resolved_model,
        "messages": _build_qwen_messages(topic),
        "temperature": 0.2,
        "max_tokens": 1200,
        "stream": False,
    }
    request = Request(
        QWEN_API_URL,
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
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen 调用失败：HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Qwen 网络请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Qwen 返回了无法解析的 JSON") from exc

    raw_text = _extract_qwen_content(payload)
    return {
        "analysis": _normalize_analysis(raw_text),
        "raw_text": raw_text,
        "images": build_video_materials(topic),
    }
