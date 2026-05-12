import json
from unittest.mock import patch

from hotstream.server import build_copy_response, build_prompts_response


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
    generate.assert_called_once_with(topic=request_payload["topic"], brief="适合公众号开头", api_key="sk-ui-test")
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
    )


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
