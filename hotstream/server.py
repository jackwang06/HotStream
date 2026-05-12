from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hotstream.copywriter import DEFAULT_GLOBAL_PROMPT, build_default_temporary_prompt, generate_copy_with_deepseek
from hotstream.image_scraper import fetch_related_images
from hotstream.scraper import SOURCE_LABELS, fetch_hot_topics

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
    }
    return aliases.get(normalized, normalized)


def build_hot_topics_response(limit: int = 20, source: str = "toutiao") -> tuple[int, dict[str, str], bytes]:
    """Build the hot topics JSON response."""
    source_key = _normalize_source(source)
    source_label = SOURCE_LABELS.get(source_key, source_key)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    try:
        topics = fetch_hot_topics(source_key, limit=limit)
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
    title = str(topic.get("title") or "").strip()
    if not title:
        return 400, headers, _json_bytes({"success": False, "error": "缺少热点标题，无法生成文案"})
    if not api_key:
        return 400, headers, _json_bytes({"success": False, "error": "请先在高级设置里填写 DeepSeek API Key"})

    try:
        kwargs: dict[str, Any] = {"topic": topic, "brief": brief, "api_key": api_key}
        if global_prompt is not None:
            kwargs["global_prompt"] = global_prompt
        if temporary_prompt is not None:
            kwargs["temporary_prompt"] = temporary_prompt
        with ThreadPoolExecutor(max_workers=2) as executor:
            copy_future = executor.submit(generate_copy_with_deepseek, **kwargs)
            images_future = executor.submit(fetch_related_images, title, limit=30)
            copy_text = copy_future.result()
            try:
                images = images_future.result()
            except Exception:
                images = []
        filename = f"{_safe_filename(title)}.txt"
        body = _json_bytes({
            "success": True,
            "copy": copy_text,
            "images": images,
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
    body = _json_bytes({
        "success": True,
        "global_prompt": DEFAULT_GLOBAL_PROMPT,
        "temporary_prompt": build_default_temporary_prompt(topic=topic, brief=brief),
    })
    return 200, headers, body


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
            if parsed.path == "/api/toutiao-hot":
                source = "toutiao"
            status, headers, body = build_hot_topics_response(limit=limit, source=source)
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
        if parsed.path in {"/api/generate-copy", "/api/prompts"}:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            if parsed.path == "/api/prompts":
                status, headers, body = build_prompts_response(raw_body)
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
