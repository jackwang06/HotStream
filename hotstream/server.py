from __future__ import annotations

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from hotstream.copywriter import DEFAULT_GLOBAL_PROMPT, build_default_temporary_prompt, generate_copy_with_deepseek
from hotstream.image_scraper import fetch_related_images
from hotstream.scraper import SOURCE_LABELS, fetch_hot_topics
from hotstream.video_analyzer import analyze_video_with_qwen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = PROJECT_ROOT / "ui"


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
    }
    return aliases.get(normalized, normalized)


def build_hot_topics_response(
    limit: int = 20,
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
        if source_key == "bilibili" or keyword or category or sort:
            fetch_kwargs.update({"keyword": keyword, "category": category, "sort": sort})
        topics = fetch_hot_topics(source_key, **fetch_kwargs)
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
    global_prompt = str(payload.get("global_prompt") or "").strip() or None
    temporary_prompt = str(payload.get("temporary_prompt") or "").strip() or None
    qwen_analysis = payload.get("qwen_analysis") if isinstance(payload.get("qwen_analysis"), dict) else None
    source_images = payload.get("source_images") if isinstance(payload.get("source_images"), list) else []
    title = str(topic.get("title") or "").strip()
    if not title:
        return 400, headers, _json_bytes({"success": False, "error": "缺少热点标题，无法生成文案"})
    if not api_key:
        return 400, headers, _json_bytes({"success": False, "error": "请先在高级设置里填写 DeepSeek API Key"})

    try:
        kwargs: dict[str, Any] = {"topic": topic, "brief": brief, "api_key": api_key, "qwen_analysis": qwen_analysis}
        if global_prompt is not None:
            kwargs["global_prompt"] = global_prompt
        if temporary_prompt is not None:
            kwargs["temporary_prompt"] = temporary_prompt
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
    body = _json_bytes({
        "success": True,
        "global_prompt": DEFAULT_GLOBAL_PROMPT,
        "temporary_prompt": build_default_temporary_prompt(topic=topic, brief=brief, qwen_analysis=qwen_analysis),
    })
    return 200, headers, body


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
    if not api_key:
        return 400, headers, _json_bytes({"success": False, "error": "请先填写 Qwen API Key"})
    if not str(topic.get("title") or "").strip():
        return 400, headers, _json_bytes({"success": False, "error": "缺少待分析的视频标题"})
    try:
        result = analyze_video_with_qwen(topic=topic, api_key=api_key, model=model)
        body = _json_bytes({
            "success": True,
            "analysis": result.get("analysis") or {},
            "raw_text": result.get("raw_text") or "",
            "images": result.get("images") or [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return 200, headers, body
    except Exception as exc:
        return 502, headers, _json_bytes({"success": False, "error": str(exc), "analysis": {}, "images": []})


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
            limit = 20
            if "limit" in params:
                try:
                    limit = max(1, min(50, int(params["limit"][0])))
                except (TypeError, ValueError):
                    limit = 20
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

        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name
        parsed = urlparse(self.path)
        if parsed.path in {"/api/generate-copy", "/api/prompts", "/api/analyze-video"}:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            if parsed.path == "/api/prompts":
                status, headers, body = build_prompts_response(raw_body)
            elif parsed.path == "/api/analyze-video":
                status, headers, body = build_video_analysis_response(raw_body)
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


def run_server(host: str = "127.0.0.1", port: int = 5173) -> None:
    server = ThreadingHTTPServer((host, port), HotStreamRequestHandler)
    print(f"HotStream running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
