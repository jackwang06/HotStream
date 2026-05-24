from __future__ import annotations

import mimetypes
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hotstream.server import (  # noqa: E402
    UI_DIR,
    _json_bytes,
    build_copy_response,
    build_hot_topics_response,
    build_prompts_response,
    build_proxy_image_response,
    build_video_analysis_response,
)


def _is_safe_static_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(UI_DIR.resolve())
        return True
    except ValueError:
        return False


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless entrypoint for HotStream."""

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, request_path: str) -> None:
        relative_path = unquote(request_path.strip("/")) or "index.html"
        static_path = (UI_DIR / relative_path).resolve()
        if not _is_safe_static_path(static_path) or not static_path.is_file():
            self._send(
                404,
                {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
                _json_bytes({"success": False, "error": "Not found"}),
            )
            return

        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type = f"{content_type}; charset=utf-8"
        self._send(
            200,
            {"Content-Type": content_type, "Cache-Control": "public, max-age=300"},
            static_path.read_bytes(),
        )

    def do_GET(self) -> None:  # noqa: N802 - Vercel handler method name
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
            self._send(
                *build_hot_topics_response(
                    limit=limit,
                    source=source,
                    keyword=keyword or None,
                    category=category or None,
                    sort=sort or None,
                )
            )
            return

        if parsed.path == "/api/proxy-image":
            params = parse_qs(parsed.query)
            image_url = params.get("url", [""])[0]
            self._send(*build_proxy_image_response(image_url))
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - Vercel handler method name
        parsed = urlparse(self.path)
        if parsed.path in {"/api/generate-copy", "/api/prompts", "/api/analyze-video"}:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            if parsed.path == "/api/prompts":
                self._send(*build_prompts_response(raw_body))
            elif parsed.path == "/api/analyze-video":
                self._send(*build_video_analysis_response(raw_body))
            else:
                self._send(*build_copy_response(raw_body))
            return

        self._send(
            404,
            {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
            _json_bytes({"success": False, "error": "Not found"}),
        )
