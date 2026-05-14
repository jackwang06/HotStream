from __future__ import annotations

import json
from pathlib import Path


def test_vercel_config_routes_to_python_handler() -> None:
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    assert config["version"] == 2
    assert config["installCommand"] == "python -V"
    assert config["buildCommand"] == "python -V"
    rewrites = config["rewrites"]
    assert {"source": "/api/(.*)", "destination": "/api/index.py"} in rewrites
    assert {"source": "/(.*)", "destination": "/api/index.py"} in rewrites


def test_vercel_python_handler_exists_and_serves_ui() -> None:
    handler = Path("api/index.py").read_text(encoding="utf-8")
    assert "class handler(BaseHTTPRequestHandler)" in handler
    assert "build_hot_topics_response" in handler
    assert "build_copy_response" in handler
    assert "build_proxy_image_response" in handler
    assert "_serve_static" in handler
    assert "UI_DIR" in handler
