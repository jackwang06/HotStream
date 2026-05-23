import json
from unittest.mock import patch

from hotstream.server import build_hot_topics_response, build_video_analysis_response


def test_build_hot_topics_response_passes_bilibili_keyword_category_sort():
    with patch("hotstream.server.fetch_hot_topics", return_value=[{"rank": 1, "title": "B站视频", "source": "B站"}]) as fetch:
        status, headers, body = build_hot_topics_response(
            source="bilibili",
            limit=10,
            keyword="草原",
            category="life",
            sort="traffic_desc",
        )

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["source"] == "B站"
    assert payload["source_key"] == "bilibili"
    assert payload["topics"][0]["title"] == "B站视频"
    fetch.assert_called_once_with("bilibili", limit=10, keyword="草原", category="life", sort="traffic_desc")


def test_build_video_analysis_response_requires_qwen_api_key():
    status, headers, body = build_video_analysis_response(json.dumps({"topic": {"title": "B站视频"}}).encode("utf-8"))

    assert status == 400
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is False
    assert "Qwen API Key" in payload["error"]


def test_build_video_analysis_response_returns_analysis_images_and_timestamp():
    request_payload = {
        "topic": {"title": "B站视频", "url": "https://www.bilibili.com/video/BVTEST", "cover": "https://example.com/cover.jpg"},
        "api_key": "qwen-key",
    }
    qwen_result = {
        "analysis": {"summary": "草原视频分析", "visual_keywords": ["草原"]},
        "raw_text": "原始分析",
        "images": [{"url": "https://example.com/cover.jpg", "thumbnail": "https://example.com/cover.jpg", "title": "B站视频封面：B站视频", "source": "B站封面"}],
    }

    with patch("hotstream.server.analyze_video_with_qwen", return_value=qwen_result) as analyze:
        status, headers, body = build_video_analysis_response(json.dumps(request_payload).encode("utf-8"))

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["success"] is True
    assert payload["analysis"]["summary"] == "草原视频分析"
    assert payload["images"][0]["source"] == "B站封面"
    assert "updated_at" in payload
    analyze.assert_called_once_with(topic=request_payload["topic"], api_key="qwen-key", model=None)
