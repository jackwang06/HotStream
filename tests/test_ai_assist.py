"""Offline unit tests for the 「AI 帮写」 (AI assist) backend.

Covers:
- copywriter.build_ai_assist_messages / generate_ai_assist for the four modes
  (expand / condense / rewrite / supplement), asserting the messages carry the
  active soul as system persona + the Markdown output instruction, and the right
  user template.
- video_analyzer.analyze_images_with_qwen builds OpenAI/DashScope-compatible
  image_url parts and returns merged analysis text.
- server.stream_ai_assist_response: the streaming NDJSON phase-event protocol
  (analyzing_images / image_failed / generating / done / error), routing per
  mode, and the rewrite-with-images path that analyzes images first then feeds
  the analysis into the rewrite.
"""

import json
from unittest.mock import patch

import pytest

from hotstream.copywriter import (
    DEFAULT_GLOBAL_PROMPT,
    MARKDOWN_OUTPUT_INSTRUCTION,
    build_ai_assist_messages,
    generate_ai_assist,
)
from hotstream.video_analyzer import (
    _build_qwen_image_analysis_messages,
    analyze_images_with_qwen,
)
from hotstream.server import stream_ai_assist_response


class _FakeWfile:
    """Minimal write-target capturing the bytes written by the handler."""

    def __init__(self):
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    def flush(self) -> None:
        pass


class _FakeHandler:
    """Lightweight stand-in for HotStreamRequestHandler for the streaming path.

    Records the status/headers and the NDJSON lines written so a test can assert
    on the emitted phase events without opening a real socket.
    """

    def __init__(self):
        self.status: int | None = None
        self.headers_sent: dict[str, str] = {}
        self.ended = False
        self.wfile = _FakeWfile()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        self.ended = True

    def events(self) -> list[dict]:
        """Parse the captured NDJSON body back into a list of event dicts."""
        body = b"".join(self.wfile.chunks).decode("utf-8")
        return [json.loads(line) for line in body.splitlines() if line.strip()]


def _run_stream(payload: dict) -> _FakeHandler:
    handler = _FakeHandler()
    stream_ai_assist_response(handler, json.dumps(payload).encode("utf-8"))
    return handler


class _FakeResponse:
    def __init__(self, content: str):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self._content}}]}).encode("utf-8")


# --------------------------------------------------------------------------- #
# copywriter.build_ai_assist_messages
# --------------------------------------------------------------------------- #


def test_build_ai_assist_messages_expand_uses_soul_and_markdown_instruction():
    messages = build_ai_assist_messages(mode="expand", selected_text="一段简短文案")

    assert messages[0]["role"] == "system"
    # Falls back to the default soul, and always appends the Markdown instruction.
    assert messages[0]["content"] == DEFAULT_GLOBAL_PROMPT + MARKDOWN_OUTPUT_INSTRUCTION
    assert messages[1]["role"] == "user"
    user = messages[1]["content"]
    assert "扩写" in user
    assert "保持原意、立场与语言风格不变" in user
    assert "用 Markdown" in user
    assert "一段简短文案" in user


def test_build_ai_assist_messages_condense_template():
    messages = build_ai_assist_messages(mode="condense", selected_text="很长很长的一段文案")

    user = messages[1]["content"]
    assert "精炼缩短" in user
    assert "保持原意与风格不变" in user
    assert "用 Markdown" in user
    assert "很长很长的一段文案" in user
    # condense must NOT carry the expand-only enrichment wording.
    assert "更充实生动" not in user


def test_build_ai_assist_messages_uses_active_soul_as_system_persona():
    messages = build_ai_assist_messages(
        mode="expand",
        selected_text="文案",
        global_prompt="你是犀利短评作者。",
    )

    assert messages[0]["content"] == "你是犀利短评作者。" + MARKDOWN_OUTPUT_INSTRUCTION


def test_build_ai_assist_messages_rewrite_threads_requirement():
    messages = build_ai_assist_messages(
        mode="rewrite",
        selected_text="原始文案内容",
        requirement="改得更口语化",
    )

    user = messages[1]["content"]
    assert "请按以下要求改写" in user
    assert "保持与全文一致的语言风格" in user
    assert "要求：改得更口语化" in user
    assert "原文案：\n原始文案内容" in user
    # No image analysis supplied -> no reference block.
    assert "参考图片分析" not in user


def test_build_ai_assist_messages_rewrite_appends_image_analysis_when_present():
    messages = build_ai_assist_messages(
        mode="rewrite",
        selected_text="原始文案内容",
        requirement="结合图片改写",
        image_analysis="图1：草原远景，可见蓝天和帐篷。",
    )

    user = messages[1]["content"]
    assert "参考图片分析（仅作参考，不要编造图中没有的事实）：" in user
    assert "图1：草原远景，可见蓝天和帐篷。" in user
    # Order: requirement, then reference block, then 原文案.
    assert user.index("要求：") < user.index("参考图片分析") < user.index("原文案：")


def test_build_ai_assist_messages_supplement_uses_context_and_requirement():
    messages = build_ai_assist_messages(
        mode="supplement",
        requirement="补一句行动号召",
        before_text="光标前的段落内容",
        after_text="光标后的段落内容",
        global_prompt="你是某风格作者。",
    )

    assert messages[0]["content"] == "你是某风格作者。" + MARKDOWN_OUTPUT_INSTRUCTION
    user = messages[1]["content"]
    assert "在不改动已有内容的前提下" in user
    assert "只输出要补充的内容本身" in user
    assert "要求：补一句行动号召" in user
    assert "【光标前文】\n光标前的段落内容" in user
    assert "【光标后文】\n光标后的段落内容" in user
    # supplement does not act on a selection.
    assert "原文案" not in user


def test_build_ai_assist_messages_rejects_unknown_mode():
    with pytest.raises(ValueError, match="未知的 AI 帮写操作"):
        build_ai_assist_messages(mode="translate", selected_text="文案")


# --------------------------------------------------------------------------- #
# copywriter.generate_ai_assist
# --------------------------------------------------------------------------- #


def test_generate_ai_assist_posts_deepseek_request_and_returns_text():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse("扩写后的成稿（Markdown）")

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        result = generate_ai_assist(
            mode="expand",
            selected_text="一段简短文案",
            api_key="test-key",
            global_prompt="你是某风格作者。",
        )

    assert result == "扩写后的成稿（Markdown）"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-chat"
    # system carries the soul + markdown instruction; user carries the selection.
    assert captured["body"]["messages"][0]["content"] == "你是某风格作者。" + MARKDOWN_OUTPUT_INSTRUCTION
    assert "一段简短文案" in captured["body"]["messages"][1]["content"]


def test_generate_ai_assist_rewrite_includes_image_analysis_in_body():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse("改写结果")

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        generate_ai_assist(
            mode="rewrite",
            selected_text="原文案",
            requirement="更活泼",
            image_analysis="图片显示草原和帐篷",
            api_key="test-key",
        )

    user = captured["body"]["messages"][1]["content"]
    assert "要求：更活泼" in user
    assert "图片显示草原和帐篷" in user


def test_generate_ai_assist_requires_api_key():
    with patch("hotstream.copywriter.load_project_env", lambda: None):
        with pytest.raises(RuntimeError, match="DeepSeek API Key"):
            generate_ai_assist(mode="expand", selected_text="文案", api_key="")


def test_generate_ai_assist_requires_selected_text():
    with patch("hotstream.copywriter.load_project_env", lambda: None):
        with pytest.raises(RuntimeError, match="没有选中"):
            generate_ai_assist(mode="expand", selected_text="   ", api_key="test-key")


def test_generate_ai_assist_supplement_posts_context_without_selection():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse("补充段落（Markdown）")

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        result = generate_ai_assist(
            mode="supplement",
            requirement="补一句行动号召",
            before_text="前文",
            after_text="后文",
            api_key="test-key",
        )

    assert result == "补充段落（Markdown）"
    user = captured["body"]["messages"][1]["content"]
    assert "要求：补一句行动号召" in user
    assert "前文" in user and "后文" in user


def test_generate_ai_assist_supplement_requires_requirement():
    with patch("hotstream.copywriter.load_project_env", lambda: None):
        with pytest.raises(RuntimeError, match="补充的具体要求"):
            generate_ai_assist(mode="supplement", requirement="  ", api_key="test-key")


# --------------------------------------------------------------------------- #
# video_analyzer.analyze_images_with_qwen
# --------------------------------------------------------------------------- #


def test_build_qwen_image_analysis_messages_uses_image_url_parts():
    messages = _build_qwen_image_analysis_messages([
        "https://example.com/a.jpg",
        "//example.com/b.jpg",
    ])

    user_content = messages[1]["content"]
    image_parts = [p for p in user_content if p["type"] == "image_url"]
    assert [p["image_url"]["url"] for p in image_parts] == [
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",  # protocol-relative gets https: prefixed
    ]
    # last part is the text instruction
    assert user_content[-1]["type"] == "text"
    assert "客观" in user_content[-1]["text"]


def test_analyze_images_with_qwen_posts_dashscope_request_and_merges_text():
    captured = {}

    class FakeQwenResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "图1：草原远景。\n图2：帐篷与人物。"}}]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeQwenResponse()

    with patch("hotstream.video_analyzer.urlopen", fake_urlopen):
        result = analyze_images_with_qwen(
            image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
            api_key="qwen-key",
        )

    assert result == "图1：草原远景。\n图2：帐篷与人物。"
    assert captured["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer qwen-key"
    assert captured["body"]["model"] == "qwen-vl-max"
    user_content = captured["body"]["messages"][1]["content"]
    image_urls = [p["image_url"]["url"] for p in user_content if p["type"] == "image_url"]
    assert image_urls == ["https://example.com/a.jpg", "https://example.com/b.jpg"]


def test_analyze_images_with_qwen_requires_api_key():
    with pytest.raises(RuntimeError, match="Qwen API Key"):
        analyze_images_with_qwen(image_urls=["https://example.com/a.jpg"], api_key="")


def test_analyze_images_with_qwen_requires_at_least_one_image():
    with pytest.raises(RuntimeError, match="没有可供分析的图片"):
        analyze_images_with_qwen(image_urls=[], api_key="qwen-key")


# --------------------------------------------------------------------------- #
# server.stream_ai_assist_response  (streaming NDJSON phase-event protocol)
# --------------------------------------------------------------------------- #


def test_stream_sends_ndjson_headers_and_status_200():
    with patch("hotstream.server.generate_ai_assist", return_value="扩写结果"):
        handler = _run_stream({"mode": "expand", "text": "文案", "api_key": "sk-deepseek"})

    assert handler.status == 200
    assert handler.ended is True
    assert handler.headers_sent["Content-Type"] == "application/x-ndjson; charset=utf-8"
    assert handler.headers_sent["Cache-Control"] == "no-store"


def test_stream_expand_emits_generating_then_done():
    request_payload = {
        "mode": "expand",
        "text": "一段简短文案",
        "global_prompt": "你是某风格作者。",
        "api_key": "sk-deepseek",
    }

    with patch("hotstream.server.generate_ai_assist", return_value="扩写结果") as generate, \
         patch("hotstream.server.analyze_images_with_qwen") as analyze:
        handler = _run_stream(request_payload)

    events = handler.events()
    assert [e["phase"] for e in events] == ["generating", "done"]
    assert events[-1] == {"phase": "done", "success": True, "text": "扩写结果"}
    analyze.assert_not_called()
    generate.assert_called_once_with(
        mode="expand",
        selected_text="一段简短文案",
        requirement="",
        image_analysis="",
        before_text="",
        after_text="",
        api_key="sk-deepseek",
        global_prompt="你是某风格作者。",
    )


def test_stream_rewrite_with_images_emits_analyzing_then_generating_then_done():
    request_payload = {
        "mode": "rewrite",
        "text": "原文案",
        "requirement": "结合图片改写",
        "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        "global_prompt": "你是某风格作者。",
        "api_key": "sk-deepseek",
        "api_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "qwen_api_key": "qwen-key",
        "qwen_api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen_model": "qwen-vl-max",
    }

    with patch("hotstream.server.analyze_images_with_qwen", return_value="图片分析文本") as analyze, \
         patch("hotstream.server.generate_ai_assist", return_value="改写结果") as generate:
        handler = _run_stream(request_payload)

    events = handler.events()
    assert [e["phase"] for e in events] == ["analyzing_images", "generating", "done"]
    assert events[-1] == {"phase": "done", "success": True, "text": "改写结果"}

    analyze.assert_called_once_with(
        image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        api_key="qwen-key",
        model="qwen-vl-max",
        api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    # The Qwen analysis is threaded into the rewrite as reference context.
    generate.assert_called_once_with(
        mode="rewrite",
        selected_text="原文案",
        requirement="结合图片改写",
        image_analysis="图片分析文本",
        before_text="",
        after_text="",
        api_key="sk-deepseek",
        global_prompt="你是某风格作者。",
        api_url="https://api.deepseek.com",
        model="deepseek-chat",
    )


def test_stream_rewrite_without_images_skips_analyzing_phase():
    request_payload = {
        "mode": "rewrite",
        "text": "原文案",
        "requirement": "更口语化",
        "images": [],
        "api_key": "sk-deepseek",
    }

    with patch("hotstream.server.analyze_images_with_qwen") as analyze, \
         patch("hotstream.server.generate_ai_assist", return_value="改写结果") as generate:
        handler = _run_stream(request_payload)

    events = handler.events()
    assert [e["phase"] for e in events] == ["generating", "done"]
    analyze.assert_not_called()
    assert generate.call_args.kwargs["image_analysis"] == ""


def test_stream_rewrite_emits_image_failed_then_continues_on_text():
    request_payload = {
        "mode": "rewrite",
        "text": "原文案",
        "requirement": "结合图片改写",
        "images": ["https://example.com/a.jpg"],
        "api_key": "sk-deepseek",
        "qwen_api_key": "",
    }

    with patch("hotstream.server.analyze_images_with_qwen", side_effect=RuntimeError("Qwen API Key 未填写")), \
         patch("hotstream.server.generate_ai_assist", return_value="改写结果") as generate:
        handler = _run_stream(request_payload)

    events = handler.events()
    assert [e["phase"] for e in events] == ["analyzing_images", "image_failed", "generating", "done"]
    assert events[-1]["success"] is True
    # Falls back to rewriting on text alone.
    assert generate.call_args.kwargs["image_analysis"] == ""


def test_stream_supplement_routes_with_context_and_no_image_phase():
    request_payload = {
        "mode": "supplement",
        "requirement": "补一句行动号召",
        "before_text": "光标前文",
        "after_text": "光标后文",
        "images": ["https://example.com/a.jpg"],  # ignored for supplement
        "global_prompt": "你是某风格作者。",
        "api_key": "sk-deepseek",
    }

    with patch("hotstream.server.analyze_images_with_qwen") as analyze, \
         patch("hotstream.server.generate_ai_assist", return_value="补充段落") as generate:
        handler = _run_stream(request_payload)

    events = handler.events()
    assert [e["phase"] for e in events] == ["generating", "done"]
    assert events[-1] == {"phase": "done", "success": True, "text": "补充段落"}
    analyze.assert_not_called()
    generate.assert_called_once_with(
        mode="supplement",
        selected_text="",
        requirement="补一句行动号召",
        image_analysis="",
        before_text="光标前文",
        after_text="光标后文",
        api_key="sk-deepseek",
        global_prompt="你是某风格作者。",
    )


def test_stream_emits_error_event_when_generation_fails():
    request_payload = {"mode": "expand", "text": "文案", "api_key": "sk-deepseek"}

    with patch("hotstream.server.generate_ai_assist", side_effect=RuntimeError("DeepSeek 调用失败")):
        handler = _run_stream(request_payload)

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert events[-1]["success"] is False
    assert "DeepSeek 调用失败" in events[-1]["error"]


def test_stream_requires_deepseek_key_emits_error_event():
    request_payload = {"mode": "expand", "text": "文案"}

    with patch("hotstream.server.generate_ai_assist") as generate:
        handler = _run_stream(request_payload)

    # Status stays 200; the error rides inside the NDJSON event.
    assert handler.status == 200
    events = handler.events()
    assert events == [{"phase": "error", "success": False, "error": "请先在设置里配置文案生成 API Key"}]
    generate.assert_not_called()


def test_stream_rejects_unknown_mode():
    handler = _run_stream({"mode": "translate", "text": "文案", "api_key": "sk-deepseek"})

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert "未知的 AI 帮写操作" in events[-1]["error"]


def test_stream_rejects_empty_selection():
    handler = _run_stream({"mode": "expand", "text": "   ", "api_key": "sk-deepseek"})

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert "选中" in events[-1]["error"]


def test_stream_rewrite_requires_requirement():
    handler = _run_stream({"mode": "rewrite", "text": "原文案", "requirement": "  ", "api_key": "sk-deepseek"})

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert "具体要求" in events[-1]["error"]


def test_stream_supplement_requires_requirement():
    handler = _run_stream({"mode": "supplement", "requirement": "  ", "api_key": "sk-deepseek"})

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert "补充的具体要求" in events[-1]["error"]


def test_stream_handles_invalid_json():
    handler = _FakeHandler()
    stream_ai_assist_response(handler, b"not json")

    events = handler.events()
    assert events[-1]["phase"] == "error"
    assert events[-1]["success"] is False

