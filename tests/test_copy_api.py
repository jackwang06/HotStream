import json
from unittest.mock import patch

from hotstream.copywriter import DEFAULT_GLOBAL_PROMPT, DEFAULT_PROMPT_TEMPLATE
from hotstream.server import (
    build_copy_response,
    build_prompt_defaults_response,
    build_prompts_response,
)


def test_build_copy_response_returns_generated_copy_and_related_images_json():
    request_payload = {
        "topic": {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
        "brief": "适合公众号开头",
        "api_key": "sk-ui-test",
    }
    image_results = [{"url": "https://example.com/a.jpg", "thumbnail": "https://example.com/a-thumb.jpg", "title": "AI 配图"}]

    with patch("hotstream.server.generate_copy_with_deepseek", return_value="生成后的文案") as generate, \
         patch("hotstream.server.fetch_related_images", return_value=image_results) as fetch_images:
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is True
    assert payload["copy"] == "生成后的文案"
    assert payload["images"] == image_results
    assert payload["filename"].endswith(".txt")
    generate.assert_called_once_with(topic=request_payload["topic"], brief="适合公众号开头", api_key="sk-ui-test", qwen_analysis=None)
    fetch_images.assert_called_once_with("AI 应用爆发", limit=30)


def test_build_copy_response_passes_prompt_overrides_to_deepseek():
    request_payload = {
        "topic": {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
        "brief": "适合公众号开头",
        "api_key": "sk-ui-test",
        "global_prompt": "你是全局角色",
        "temporary_prompt": "这一次只写三句话",
    }

    with patch("hotstream.server.generate_copy_with_deepseek", return_value="生成后的文案") as generate:
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    assert status == 200
    generate.assert_called_once_with(
        topic=request_payload["topic"],
        brief="适合公众号开头",
        api_key="sk-ui-test",
        global_prompt="你是全局角色",
        temporary_prompt="这一次只写三句话",
        qwen_analysis=None,
    )


def test_build_copy_response_passes_qwen_analysis_and_video_images():
    request_payload = {
        "topic": {"title": "草原旅行视频", "source": "B站", "cover": "https://example.com/cover.jpg"},
        "brief": "写成前山牧场推广推文",
        "api_key": "sk-ui-test",
        "qwen_analysis": {"summary": "草原松弛感", "visual_keywords": ["草原"]},
        "source_images": [{"url": "https://example.com/cover.jpg", "thumbnail": "https://example.com/cover.jpg", "title": "B站视频封面", "source": "B站封面"}],
    }

    with patch("hotstream.server.generate_copy_with_deepseek", return_value="生成后的文案") as generate, \
         patch("hotstream.server.fetch_related_images", return_value=[]) as fetch_images:
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["images"][0]["source"] == "B站封面"
    assert payload["draft"]["topic"]["source"] == "B站"
    assert payload["draft"]["analysis"]["summary"] == "草原松弛感"
    assert "前山牧场四季牧歌" in payload["draft"]["title"]
    generate.assert_called_once_with(
        topic=request_payload["topic"],
        brief="写成前山牧场推广推文",
        api_key="sk-ui-test",
        qwen_analysis=request_payload["qwen_analysis"],
    )
    fetch_images.assert_called_once_with("草原旅行视频", limit=30)


def test_build_copy_response_requires_api_key_from_advanced_settings():
    request_payload = {
        "topic": {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
        "brief": "适合公众号开头",
    }

    with patch("hotstream.server.generate_copy_with_deepseek") as generate:
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    assert status == 400
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is False
    assert "DeepSeek API Key" in payload["error"]
    generate.assert_not_called()


def test_build_prompts_response_exposes_global_and_temporary_prompts():
    topic = {"title": "AI 应用爆发", "source": "知乎", "hot_value": 12345}
    raw_body = json.dumps({"topic": topic, "brief": "300 字以内"}).encode("utf-8")

    status, headers, body = build_prompts_response(raw_body)

    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is True
    assert "global_prompt" in payload
    assert "temporary_prompt" in payload
    assert "AI 应用爆发" in payload["temporary_prompt"]
    assert "300 字以内" in payload["temporary_prompt"]


def test_build_copy_response_passes_default_prompt_to_deepseek():
    request_payload = {
        "topic": {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
        "brief": "适合公众号开头",
        "api_key": "sk-ui-test",
        "default_prompt": "自定义模板XYZ",
    }

    with patch("hotstream.server.generate_copy_with_deepseek", return_value="生成后的文案") as generate, \
         patch("hotstream.server.fetch_related_images", return_value=[]):
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    assert status == 200
    generate.assert_called_once_with(
        topic=request_payload["topic"],
        brief="适合公众号开头",
        api_key="sk-ui-test",
        qwen_analysis=None,
        default_prompt="自定义模板XYZ",
    )


def test_build_copy_response_omits_empty_default_prompt():
    request_payload = {
        "topic": {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
        "brief": "适合公众号开头",
        "api_key": "sk-ui-test",
        "default_prompt": "",
    }

    with patch("hotstream.server.generate_copy_with_deepseek", return_value="生成后的文案") as generate, \
         patch("hotstream.server.fetch_related_images", return_value=[]):
        build_copy_response(json.dumps(request_payload).encode("utf-8"))

    # Empty/whitespace default_prompt must not be forwarded (falls back to template).
    assert "default_prompt" not in generate.call_args.kwargs


def test_build_prompts_response_reflects_custom_default_prompt():
    topic = {"title": "AI 应用爆发", "source": "知乎", "hot_value": 12345}
    raw_body = json.dumps({"topic": topic, "brief": "300 字以内", "default_prompt": "自定义模板XYZ"}).encode("utf-8")

    status, headers, body = build_prompts_response(raw_body)

    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is True
    # global_prompt stays the factory soul; temporary_prompt reflects the custom scaffold.
    assert payload["global_prompt"] == DEFAULT_GLOBAL_PROMPT
    assert "自定义模板XYZ" in payload["temporary_prompt"]
    assert "请基于以下热点写一篇可直接发布的中文推文" not in payload["temporary_prompt"]
    # Dynamic materials still injected around the custom scaffold.
    assert "AI 应用爆发" in payload["temporary_prompt"]
    assert "300 字以内" in payload["temporary_prompt"]


def test_build_prompts_response_default_path_uses_factory_template():
    topic = {"title": "AI 应用爆发", "source": "知乎", "hot_value": 12345}
    raw_body = json.dumps({"topic": topic, "brief": "300 字以内"}).encode("utf-8")

    status, headers, body = build_prompts_response(raw_body)

    payload = json.loads(body.decode("utf-8"))
    assert "请基于以下热点写一篇可直接发布的中文推文" in payload["temporary_prompt"]
    # Output format is now Markdown-style with ## headings.
    assert "## 结尾" in payload["temporary_prompt"]
    assert "一句互动式收束，引导评论或转发" in payload["temporary_prompt"]


def test_build_prompt_defaults_returns_factory_soul_and_prompt():
    status, headers, body = build_prompt_defaults_response()

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is True
    assert payload["default_soul"] == DEFAULT_GLOBAL_PROMPT
    assert payload["default_prompt"] == DEFAULT_PROMPT_TEMPLATE


def test_build_copy_response_rejects_missing_topic_title():
    status, headers, body = build_copy_response(json.dumps({"topic": {}, "brief": ""}).encode("utf-8"))

    assert status == 400
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is False
    assert "热点标题" in payload["error"]


def test_build_copy_response_handles_deepseek_error():
    request_payload = {"topic": {"title": "AI 应用爆发"}, "brief": "", "api_key": "sk-ui-test"}

    with patch("hotstream.server.generate_copy_with_deepseek", side_effect=RuntimeError("DEEPSEEK_API_KEY 未配置")):
        status, headers, body = build_copy_response(json.dumps(request_payload).encode("utf-8"))

    assert status == 502
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is False
    assert "DEEPSEEK_API_KEY" in payload["error"]
