from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from hotstream.copywriter import (
    DEFAULT_GLOBAL_PROMPT,
    DEFAULT_PROMPT_TEMPLATE,
    build_default_temporary_prompt,
    generate_ai_assist,
    generate_copy_with_deepseek,
    restore_topic_full_picture,
    select_relevant_topics,
)
from hotstream.web_search import search_web_snippets
from hotstream.image_scraper import build_custom_topic, fetch_related_images
from hotstream.scraper import SOURCE_LABELS, fetch_hot_topics
from hotstream.video_analyzer import analyze_images_with_qwen, analyze_video_with_qwen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Single frontend source: the production-served files under web/legacy/. The
# Python/Vercel standalone modes serve the same files (they used to point at a
# now-removed ui/ copy that drifted out of sync with production).
UI_DIR = PROJECT_ROOT / "web" / "legacy"


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _normalize_source(source: str) -> str:
    normalized = (source or "toutiao").strip().lower()
    aliases = {
        "今日头条": "toutiao",
        "toutiao": "toutiao",
        "知乎": "zhihu",
        "zhihu": "zhihu",
        "小红书": "xiaohongshu",
        "xiaohongshu": "xiaohongshu",
        "xhs": "xiaohongshu",
        "bilibili": "bilibili",
        "b站": "bilibili",
        "哔哩哔哩": "bilibili",
        "bili": "bilibili",
        "douyin": "douyin",
        "抖音": "douyin",
        "dy": "douyin",
    }
    return aliases.get(normalized, normalized)


# ── 热点抓取：进程内短 TTL 缓存 ─────────────────────────────────────────────
# 每次进页面 + 每 60s 自动刷新 + 精选聚合五源，都会反复抓同一批源站；加一个进程内
# TTL 缓存，让窗口期内的重复请求（同一用户的自动刷新、多用户、精选并发）直接命中，
# 大幅减少对源站的真实请求与延迟/风控压力。TTL 可用 HOT_TOPICS_CACHE_TTL 调（秒，默认 60）。
# ThreadingHTTPServer 多线程并发，故用锁保护；命中/写入都用深拷贝隔离，避免调用方对
# 返回值的改动（如加 rank / 覆盖 source 标签）污染缓存。抓取在锁外进行，不阻塞其它线程。
HOT_TOPICS_CACHE_TTL = float(os.getenv("HOT_TOPICS_CACHE_TTL", "60"))
_hot_topics_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_hot_topics_cache_lock = threading.Lock()


def _hot_topics_cache_key(source: str, kwargs: dict[str, Any]) -> tuple:
    """稳定缓存键：来源(归一化) + 非空参数排序。None/'' 视为未指定，使“只传 limit”与
    “传了 limit 且 keyword=None”落到同一条目。"""
    norm = (source or "toutiao").strip().lower()
    items = tuple(sorted((k, v) for k, v in kwargs.items() if v not in (None, "")))
    return (norm, items)


def fetch_hot_topics_cached(
    source: str = "toutiao",
    *,
    ttl: float | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """带进程内 TTL 缓存的 fetch_hot_topics。ttl<=0 直接透传不缓存。

    内部调用模块级 ``fetch_hot_topics`` 名字（单测 patch 该名字仍然生效）。失败不缓存。
    """
    effective_ttl = HOT_TOPICS_CACHE_TTL if ttl is None else ttl
    if effective_ttl <= 0:
        return fetch_hot_topics(source, **kwargs)

    key = _hot_topics_cache_key(source, kwargs)
    with _hot_topics_cache_lock:
        cached = _hot_topics_cache.get(key)
        if cached is not None and (time.monotonic() - cached[0]) < effective_ttl:
            return copy.deepcopy(cached[1])  # 隔离副本，调用方可随意改动

    # 未命中：锁外抓取（慢网络不持锁），成功后写入一份隔离副本。
    topics = fetch_hot_topics(source, **kwargs)
    with _hot_topics_cache_lock:
        _hot_topics_cache[key] = (time.monotonic(), copy.deepcopy(topics))
    return topics


def clear_hot_topics_cache() -> None:
    """清空热点缓存（测试隔离用，或需要强制刷新时）。"""
    with _hot_topics_cache_lock:
        _hot_topics_cache.clear()


def build_hot_topics_response(
    limit: int = 30,
    source: str = "toutiao",
    keyword: str | None = None,
    category: str | None = None,
    sort: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Build the hot topics JSON response."""
    source_key = _normalize_source(source)
    source_label = SOURCE_LABELS.get(source_key, source_key)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        fetch_kwargs: dict[str, Any] = {"limit": limit}
        # Forward keyword/category/sort whenever the user supplied any of them
        # (category now drives filtering on every source) or for the video
        # sources whose native dispatch always accepts these arguments.
        if source_key in {"bilibili", "douyin"} or keyword or category or sort:
            fetch_kwargs.update({"keyword": keyword, "category": category, "sort": sort})
        topics = fetch_hot_topics_cached(source_key, **fetch_kwargs)
        body = _json_bytes({
            "success": True,
            "source": source_label,
            "source_key": source_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "topics": topics,
        })
        return 200, headers, body
    except Exception as exc:
        body = _json_bytes({
            "success": False,
            "source": source_label,
            "source_key": source_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "topics": [],
        })
        return 502, headers, body


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value).strip("-")
    return (safe or "hotstream-copy")[:48]


def build_copy_response(raw_body: bytes) -> tuple[int, dict[str, str], bytes]:
    """Build the /api/generate-copy JSON response."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return 400, headers, _json_bytes({"success": False, "error": "请求 JSON 格式不正确"})

    topic = payload.get("topic") or {}
    brief = str(payload.get("brief") or "")
    api_key = str(payload.get("api_key") or "").strip()
    api_url = str(payload.get("api_url") or "").strip() or None
    model = str(payload.get("model") or "").strip() or None
    global_prompt = str(payload.get("global_prompt") or "").strip() or None
    temporary_prompt = str(payload.get("temporary_prompt") or "").strip() or None
    default_prompt = str(payload.get("default_prompt") or "").strip() or None
    knowledge_base = str(payload.get("knowledge_base") or "")
    qwen_analysis = payload.get("qwen_analysis") if isinstance(payload.get("qwen_analysis"), dict) else None
    source_images = payload.get("source_images") if isinstance(payload.get("source_images"), list) else []
    title = str(topic.get("title") or "").strip()
    if not title:
        return 400, headers, _json_bytes({"success": False, "error": "缺少热点标题，无法生成文案"})
    if not api_key:
        return 400, headers, _json_bytes({"success": False, "error": "请先在高级设置里填写 DeepSeek API Key"})

    try:
        kwargs: dict[str, Any] = {"topic": topic, "brief": brief, "api_key": api_key, "qwen_analysis": qwen_analysis}
        if api_url is not None:
            kwargs["api_url"] = api_url
        if model is not None:
            kwargs["model"] = model
        if global_prompt is not None:
            kwargs["global_prompt"] = global_prompt
        if temporary_prompt is not None:
            kwargs["temporary_prompt"] = temporary_prompt
        if default_prompt is not None:
            kwargs["default_prompt"] = default_prompt
        if knowledge_base:
            kwargs["knowledge_base"] = knowledge_base
        with ThreadPoolExecutor(max_workers=2) as executor:
            copy_future = executor.submit(generate_copy_with_deepseek, **kwargs)
            images_future = executor.submit(fetch_related_images, title, limit=30)
            copy_text = copy_future.result()
            try:
                related_images = images_future.result()
            except Exception:
                related_images = []
        images = [item for item in source_images if isinstance(item, dict)] + related_images
        filename = f"{_safe_filename(title)}.txt"
        draft = {
            "title": f"前山牧场四季牧歌｜{title}",
            "content": copy_text,
            "topic": topic,
            "images": images,
            "analysis": qwen_analysis,
            "blocks": [],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        body = _json_bytes({
            "success": True,
            "copy": copy_text,
            "images": images,
            "draft": draft,
            "filename": filename,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return 200, headers, body
    except Exception as exc:
        body = _json_bytes({
            "success": False,
            "error": str(exc),
            "copy": "",
        })
        return 502, headers, body


# 精选热点聚合时每个数据源抓取的条数，以及参与精选的并发源。
CURATED_SOURCES = ("toutiao", "zhihu", "xiaohongshu", "bilibili", "douyin")
CURATED_PER_SOURCE_LIMIT = 25


def build_curated_topics_response(raw_body: bytes) -> tuple[int, dict[str, str], bytes]:
    """Build the /api/curated-topics JSON response.

    Concurrently best-effort fetches the five hot-topic sources, aggregates them
    into a single numbered pool (each topic keeps its original ``source``), then
    asks DeepSeek (via ``select_relevant_topics``) to curate the entries most
    suitable for借势-marketing the venue, using the scenic profile + knowledge
    base. Returns ``{success, topics:[...含 source+reason]}``. A missing DeepSeek
    key is a friendly 400; any other failure is a 502.
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return 400, headers, _json_bytes({"success": False, "error": "请求 JSON 格式不正确"})

    api_key = str(payload.get("api_key") or "").strip()
    api_url = str(payload.get("api_url") or "").strip() or None
    model = str(payload.get("model") or "").strip() or None
    knowledge_base = str(payload.get("knowledge_base") or "")
    if not api_key:
        return 400, headers, _json_bytes(
            {"success": False, "error": "请先在设置配置文案生成 API Key", "topics": []}
        )

    try:
        # Best-effort concurrent fetch of every source; a single source failing
        # (network / anti-bot) is skipped rather than failing the whole curation.
        def _fetch(source: str) -> list[dict[str, Any]]:
            try:
                return fetch_hot_topics_cached(source, limit=CURATED_PER_SOURCE_LIMIT)
            except Exception:
                return []

        aggregated: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(CURATED_SOURCES)) as executor:
            for source_topics in executor.map(_fetch, CURATED_SOURCES):
                for topic in source_topics:
                    if isinstance(topic, dict) and str(topic.get("title") or "").strip():
                        aggregated.append(topic)
        # Give each aggregated topic a stable global rank for display.
        for index, topic in enumerate(aggregated, start=1):
            topic["rank"] = index

        if not aggregated:
            return 502, headers, _json_bytes(
                {"success": False, "error": "暂时未能抓取到任何热点，请稍后再试", "topics": []}
            )

        selected = select_relevant_topics(
            aggregated,
            knowledge_base=knowledge_base,
            api_key=api_key,
            model=model,
            api_url=api_url,
        )
        # Re-rank the curated subset so the frontend shows 1..n in selection order.
        for index, topic in enumerate(selected, start=1):
            topic["rank"] = index
        body = _json_bytes({
            "success": True,
            "topics": selected,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return 200, headers, body
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc), "topics": []})


def build_prompts_response(raw_body: bytes) -> tuple[int, dict[str, str], bytes]:
    """Build default prompt payload for the advanced settings UI."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return 400, headers, _json_bytes({"success": False, "error": "请求 JSON 格式不正确"})

    topic = payload.get("topic") or {}
    brief = str(payload.get("brief") or "")
    qwen_analysis = payload.get("qwen_analysis") if isinstance(payload.get("qwen_analysis"), dict) else None
    default_prompt = str(payload.get("default_prompt") or "").strip() or None
    body = _json_bytes({
        "success": True,
        "global_prompt": DEFAULT_GLOBAL_PROMPT,
        "temporary_prompt": build_default_temporary_prompt(
            topic=topic,
            brief=brief,
            qwen_analysis=qwen_analysis,
            default_prompt=default_prompt,
        ),
    })
    return 200, headers, body


def build_prompt_defaults_response() -> tuple[int, dict[str, str], bytes]:
    """Return the factory-default 代理灵魂 / 默认提示词 sourced from Python.

    ``default_soul`` is the AI persona (DEFAULT_GLOBAL_PROMPT);
    ``default_prompt`` is the instruction scaffold (DEFAULT_PROMPT_TEMPLATE).
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    body = _json_bytes({
        "success": True,
        "default_soul": DEFAULT_GLOBAL_PROMPT,
        "default_prompt": DEFAULT_PROMPT_TEMPLATE,
    })
    return 200, headers, body


def build_custom_source_response(url: str, timeout: int = 10) -> tuple[int, dict[str, str], bytes]:
    """Build the /api/custom-source JSON response for a user-pasted link.

    Fetches the URL, extracts a single topic (title/cover/desc) and reports
    whether the page carries a video so the UI can offer video analysis.
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    target = str(url or "").strip()
    if not target.startswith(("http://", "https://")):
        return 400, headers, _json_bytes({"success": False, "error": "链接必须以 http:// 或 https:// 开头"})
    try:
        topic = build_custom_topic(target, timeout=timeout)
        body = _json_bytes({
            "success": True,
            "topic": topic,
            "has_video": bool(topic.get("has_video")),
        })
        return 200, headers, body
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc)})


def build_video_analysis_response(raw_body: bytes) -> tuple[int, dict[str, str], bytes]:
    """Build the /api/analyze-video JSON response."""
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return 400, headers, _json_bytes({"success": False, "error": "请求 JSON 格式不正确"})
    topic = payload.get("topic") or {}
    api_key = str(payload.get("api_key") or "").strip()
    model = str(payload.get("model") or "").strip() or None
    api_url = str(payload.get("api_url") or "").strip() or None
    # DeepSeek 用于②联网检索后的③还原全貌；缺这组 Key 则只返回 Qwen 概况（降级）。
    deepseek_api_key = str(payload.get("deepseek_api_key") or "").strip()
    deepseek_api_url = str(payload.get("deepseek_api_url") or "").strip() or None
    deepseek_model = str(payload.get("deepseek_model") or "").strip() or None
    title = str(topic.get("title") or "").strip()
    if not api_key:
        return 400, headers, _json_bytes({"success": False, "error": "请先填写 Qwen API Key"})
    if not title:
        return 400, headers, _json_bytes({"success": False, "error": "缺少待分析的视频标题"})

    # ① Qwen-VL 看封面+标题+简介 → 概况（失败则整体 502，与原行为一致）。
    try:
        result = analyze_video_with_qwen(topic=topic, api_key=api_key, model=model, api_url=api_url)
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc), "analysis": {}, "images": []})

    analysis = result.get("analysis") or {}
    raw_text = result.get("raw_text") or ""
    images = result.get("images") or []
    overview = (raw_text or str(analysis.get("summary") or "")).strip()

    # ②联网检索 + ③DeepSeek 还原全貌（均 best-effort，任一失败降级回 Qwen 概况）。
    inferred = ""
    sources_hit: list[str] = []
    if deepseek_api_key:
        try:
            search = search_web_snippets(title)
        except Exception:
            search = {"snippets": [], "sources_hit": []}
        sources_hit = search.get("sources_hit") or []
        try:
            inferred = restore_topic_full_picture(
                title=title,
                source=str(topic.get("source") or ""),
                overview=overview,
                snippets=search.get("snippets") or [],
                api_key=deepseek_api_key,
                model=deepseek_model,
                api_url=deepseek_api_url,
                timeout=30,
            )
        except Exception:
            inferred = ""

    body = _json_bytes({
        "success": True,
        "analysis": analysis,
        "raw_text": raw_text,
        "overview": overview,
        "inferred": inferred,          # DeepSeek 还原的全貌(推断, 前端可编辑); 空则前端用 raw_text 降级
        "sources_hit": sources_hit,    # 实际命中的联网检索源(头条/百度/知乎)
        "images": images,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return 200, headers, body


def stream_ai_assist_response(handler: "HotStreamRequestHandler", raw_body: bytes) -> None:
    """Stream the /api/ai-assist response for the editor's 「AI 帮写」 feature.

    Emits a sequence of NDJSON (application/x-ndjson) phase events so the editor
    can drive a progress indicator instead of treating the call as a black box:

    - ``{"phase":"error","success":false,"error":...}``  — validation/runtime error
      (HTTP status stays 200; the error travels inside the event).
    - ``{"phase":"analyzing_images"}``                    — Qwen image read started
      (only for ``rewrite`` with images).
    - ``{"phase":"image_failed"}``                        — image read failed, best
      effort; generation continues on text alone.
    - ``{"phase":"generating"}``                          — DeepSeek generation started.
    - ``{"phase":"done","success":true,"text":<markdown>}`` — final result.

    Parses ``mode``/``text``/``requirement``/``images`` (expand/condense/rewrite)
    or ``requirement``/``before_text``/``after_text`` (supplement) plus the
    injected credentials (DeepSeek for generation, Qwen for image analysis) and
    the active soul (``global_prompt``). ``supplement`` does not touch images.
    """
    # Send the streaming response headers up front; every event is written and
    # flushed immediately so the browser's reader sees phases as they happen.
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()

    def emit(event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        try:
            handler.wfile.write(line.encode("utf-8"))
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Client navigated away / cancelled the fetch; stop quietly.
            raise

    try:
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            emit({"phase": "error", "success": False, "error": "请求 JSON 格式不正确"})
            return

        mode = str(payload.get("mode") or "").strip().lower()
        text = str(payload.get("text") or "")
        requirement = str(payload.get("requirement") or "")
        before_text = str(payload.get("before_text") or "")
        after_text = str(payload.get("after_text") or "")
        images = [str(url).strip() for url in payload.get("images") or [] if str(url).strip()]
        global_prompt = str(payload.get("global_prompt") or "").strip() or None

        api_key = str(payload.get("api_key") or "").strip()
        api_url = str(payload.get("api_url") or "").strip() or None
        model = str(payload.get("model") or "").strip() or None

        qwen_api_key = str(payload.get("qwen_api_key") or "").strip()
        qwen_api_url = str(payload.get("qwen_api_url") or "").strip() or None
        qwen_model = str(payload.get("qwen_model") or "").strip() or None

        if mode not in {"expand", "condense", "rewrite", "supplement"}:
            emit({"phase": "error", "success": False, "error": "未知的 AI 帮写操作"})
            return
        if mode == "supplement":
            if not requirement.strip():
                emit({"phase": "error", "success": False, "error": "请填写补充的具体要求"})
                return
        else:
            if not text.strip():
                emit({"phase": "error", "success": False, "error": "请先选中要处理的文案"})
                return
            if mode == "rewrite" and not requirement.strip():
                emit({"phase": "error", "success": False, "error": "请填写改写的具体要求"})
                return
        if not api_key:
            emit({"phase": "error", "success": False, "error": "请先在设置里配置文案生成 API Key"})
            return

        image_analysis = ""
        if mode == "rewrite" and images:
            emit({"phase": "analyzing_images"})
            try:
                image_analysis = analyze_images_with_qwen(
                    image_urls=images,
                    api_key=qwen_api_key,
                    model=qwen_model,
                    api_url=qwen_api_url,
                )
            except Exception:
                # Image analysis is best-effort context; if Qwen fails (no key,
                # network, etc.) continue rewriting on text alone.
                image_analysis = ""
                emit({"phase": "image_failed"})

        kwargs: dict[str, Any] = {
            "mode": mode,
            "selected_text": text,
            "requirement": requirement,
            "image_analysis": image_analysis,
            "before_text": before_text,
            "after_text": after_text,
            "api_key": api_key,
        }
        if global_prompt is not None:
            kwargs["global_prompt"] = global_prompt
        if api_url is not None:
            kwargs["api_url"] = api_url
        if model is not None:
            kwargs["model"] = model

        emit({"phase": "generating"})
        try:
            result_text = generate_ai_assist(**kwargs)
        except Exception as exc:
            emit({"phase": "error", "success": False, "error": str(exc)})
            return
        emit({"phase": "done", "success": True, "text": result_text})
    except (BrokenPipeError, ConnectionResetError):
        # Client closed the connection mid-stream; nothing more to do.
        return


def build_proxy_image_response(image_url: str, timeout: int = 12) -> tuple[int, dict[str, str], bytes]:
    """Fetch a remote image and return it from the same origin for canvas export."""
    json_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    parsed = urlparse(str(image_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return 400, json_headers, _json_bytes({"success": False, "error": "图片地址必须是 http 或 https URL"})

    try:
        request = urllib.request.Request(
            parsed.geturl(),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
            body = response.read()
    except URLError as exc:
        return 502, json_headers, _json_bytes({"success": False, "error": str(exc.reason or exc)})
    except Exception as exc:
        return 502, json_headers, _json_bytes({"success": False, "error": str(exc)})

    if not content_type.startswith("image/"):
        return 415, json_headers, _json_bytes({"success": False, "error": "远程资源不是 image 图片内容"})

    return 200, {
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=86400",
    }, body


class HotStreamRequestHandler(SimpleHTTPRequestHandler):
    """Serve the prototype UI and a small JSON API."""

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name
        parsed = urlparse(self.path)
        if parsed.path in {"/api/toutiao-hot", "/api/hot-topics"}:
            params = parse_qs(parsed.query)
            limit = 30
            if "limit" in params:
                try:
                    limit = max(1, min(100, int(params["limit"][0])))
                except (TypeError, ValueError):
                    limit = 30
            source = params.get("source", ["toutiao"])[0]
            keyword = params.get("keyword", [""])[0]
            category = params.get("category", [""])[0]
            sort = params.get("sort", [""])[0]
            if parsed.path == "/api/toutiao-hot":
                source = "toutiao"
            status, headers, body = build_hot_topics_response(
                limit=limit,
                source=source,
                keyword=keyword or None,
                category=category or None,
                sort=sort or None,
            )
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/custom-source":
            params = parse_qs(parsed.query)
            custom_url = params.get("url", [""])[0]
            status, headers, body = build_custom_source_response(custom_url)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/proxy-image":
            params = parse_qs(parsed.query)
            image_url = params.get("url", [""])[0]
            status, headers, body = build_proxy_image_response(image_url)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/settings":
            status, headers, body = build_settings_get_response()
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/prompt-defaults":
            status, headers, body = build_prompt_defaults_response()
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/drafts" or parsed.path.startswith("/api/drafts/"):
            draft_id = None
            if parsed.path.startswith("/api/drafts/"):
                try:
                    draft_id = int(parsed.path.rsplit("/", 1)[-1])
                except (ValueError, IndexError):
                    pass
            status, headers, body = build_drafts_crud_response("GET", raw_body=b"", draft_id=draft_id)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/history":
            status, headers, body = build_history_response("GET", raw_body=b"")
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name
        parsed = urlparse(self.path)
        if parsed.path in {"/api/generate-copy", "/api/curated-topics", "/api/prompts", "/api/analyze-video", "/api/ai-assist", "/api/settings", "/api/drafts", "/api/history"}:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            # /api/ai-assist is special: it streams NDJSON phase events directly
            # to the socket (its own send_response(200) + per-line flush), rather
            # than going through the buffered (status, headers, body) path below.
            if parsed.path == "/api/ai-assist":
                stream_ai_assist_response(self, raw_body)
                return
            if parsed.path == "/api/curated-topics":
                status, headers, body = build_curated_topics_response(raw_body)
            elif parsed.path == "/api/prompts":
                status, headers, body = build_prompts_response(raw_body)
            elif parsed.path == "/api/analyze-video":
                status, headers, body = build_video_analysis_response(raw_body)
            elif parsed.path == "/api/settings":
                status, headers, body = build_settings_save_response(raw_body)
            elif parsed.path == "/api/drafts":
                status, headers, body = build_drafts_crud_response("POST", raw_body=raw_body)
            elif parsed.path == "/api/history":
                status, headers, body = build_history_response("POST", raw_body=raw_body)
            else:
                status, headers, body = build_copy_response(raw_body)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(_json_bytes({"success": False, "error": "Not found"}))


def build_settings_get_response() -> tuple[int, dict[str, str], bytes]:
    """GET /api/settings — return saved settings or defaults."""
    from hotstream.db import connect_db, load_settings  # noqa: E402
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    try:
        conn = connect_db()
        saved = load_settings(conn)
        conn.close()
    except Exception:
        saved = None
    deepseek_key = saved.deepseek_api_key if saved else ""
    qwen_key = saved.qwen_api_key if saved else ""
    return 200, headers, _json_bytes({
        "success": True,
        "deepseek_api_key": deepseek_key,
        "qwen_api_key": qwen_key,
        # 与 Next.js /api/settings 契约对齐：前端用 has* 判断是否已配置（独立 Python
        # standalone 路径也能正确点亮生成/分析按钮，不再恒为未配置）。
        "hasDeepseekKey": bool(deepseek_key),
        "hasQwenKey": bool(qwen_key),
        "global_prompt": saved.global_prompt if (saved and saved.global_prompt) else DEFAULT_GLOBAL_PROMPT,
    })


def build_settings_save_response(raw_body: bytes) -> tuple[int, dict[str, str], bytes]:
    """POST /api/settings — save settings to DB."""
    from hotstream.db import connect_db, load_settings, save_settings  # noqa: E402
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, headers, _json_bytes({"success": False, "error": "Invalid JSON"})
    try:
        conn = connect_db()
        save_settings(
            conn,
            deepseek_api_key=str(payload.get("deepseek_api_key", "")).strip(),
            qwen_api_key=str(payload.get("qwen_api_key", "")).strip(),
            global_prompt=str(payload.get("global_prompt", "")).strip(),
        )
        # return the saved values
        saved = load_settings(conn)
        conn.close()
        return 200, headers, _json_bytes({
            "success": True,
            "deepseek_api_key": saved.deepseek_api_key if saved else "",
            "qwen_api_key": saved.qwen_api_key if saved else "",
            "global_prompt": saved.global_prompt if (saved and saved.global_prompt) else DEFAULT_GLOBAL_PROMPT,
        })
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc)})


def build_drafts_crud_response(
    method: str,
    raw_body: bytes,
    draft_id: int | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """GET/POST/PUT/DELETE /api/drafts[/<id>]."""
    from hotstream.db import connect_db, create_draft, delete_draft, get_all_drafts, get_draft, update_draft  # noqa: E402
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    try:
        conn = connect_db()
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc)})
    try:
        if method == "GET":
            if draft_id is not None:
                draft = get_draft(conn, draft_id=draft_id)
                result = {"success": True, "draft": _draft_row_to_dict(draft)} if draft else {"success": False, "error": "Draft not found"}
                status = 200 if draft else 404
            else:
                drafts = get_all_drafts(conn)
                result = {"success": True, "drafts": [_draft_row_to_dict(d) for d in drafts]}
                status = 200
        elif method == "POST":
            payload = json.loads(raw_body.decode("utf-8"))
            draft = create_draft(
                conn,
                title=str(payload.get("title", "")).strip(),
                content_blocks=json.dumps(payload.get("content_blocks", [])),
                images=json.dumps(payload.get("images", [])),
            )
            result = {"success": True, "draft": _draft_row_to_dict(draft)}
            status = 200
        elif method == "PUT":
            if draft_id is None:
                return 400, headers, _json_bytes({"success": False, "error": "Missing draft ID"})
            payload = json.loads(raw_body.decode("utf-8"))
            draft = update_draft(
                conn,
                draft_id=draft_id,
                title=str(payload.get("title", "")).strip(),
                content_blocks=json.dumps(payload.get("content_blocks", [])),
                images=json.dumps(payload.get("images", [])),
            )
            result = {"success": True, "draft": _draft_row_to_dict(draft)}
            status = 200
        elif method == "DELETE":
            if draft_id is None:
                return 400, headers, _json_bytes({"success": False, "error": "Missing draft ID"})
            delete_draft(conn, draft_id=draft_id)
            result = {"success": True}
            status = 200
        else:
            return 405, headers, _json_bytes({"success": False, "error": "Method not allowed"})
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
        status = 502
    finally:
        conn.close()
    return status, headers, _json_bytes(result)


def _draft_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "content_blocks": json.loads(row.content_blocks) if row.content_blocks else [],
        "images": json.loads(row.images) if row.images else [],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def build_history_response(
    method: str,
    raw_body: bytes,
) -> tuple[int, dict[str, str], bytes]:
    """GET/POST /api/history."""
    from hotstream.db import connect_db, get_history, record_history  # noqa: E402
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    try:
        conn = connect_db()
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc)})
    try:
        if method == "GET":
            rows = get_history(conn, limit=50)
            result = {
                "success": True,
                "history": [
                    {
                        "id": r.id,
                        "topic_title": r.topic_title,
                        "copy_text": r.copy_text,
                        "hot_value": r.hot_value,
                        "source": r.source,
                        "chars": r.chars,
                        "created_at": r.created_at,
                    }
                    for r in rows
                ],
            }
            status = 200
        elif method == "POST":
            payload = json.loads(raw_body.decode("utf-8"))
            row = record_history(
                conn,
                topic_title=str(payload.get("topic_title", "")),
                copy_text=str(payload.get("copy_text", "")),
                hot_value=str(payload.get("hot_value", "")),
                source=str(payload.get("source", "")),
                chars=int(payload.get("chars", 0)),
            )
            result = {"success": True, "id": row.id}
            status = 200
        else:
            return 405, headers, _json_bytes({"success": False, "error": "Method not allowed"})
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
        status = 502
    finally:
        conn.close()
    return status, headers, _json_bytes(result)


def run_server(host: str = "127.0.0.1", port: int = 5173) -> None:
    server = ThreadingHTTPServer((host, port), HotStreamRequestHandler)
    print(f"HotStream running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
