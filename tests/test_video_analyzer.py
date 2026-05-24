import json
from unittest.mock import patch

import pytest

from hotstream.video_analyzer import analyze_video_with_qwen, build_video_materials


def test_build_video_materials_uses_bilibili_cover_as_editable_material():
    topic = {
        "title": "草原旅行视频",
        "cover": "https://i0.hdslb.com/bfs/archive/cover.jpg",
        "url": "https://www.bilibili.com/video/BVTEST",
    }

    materials = build_video_materials(topic)

    assert materials == [
        {
            "url": "https://i0.hdslb.com/bfs/archive/cover.jpg",
            "thumbnail": "https://i0.hdslb.com/bfs/archive/cover.jpg",
            "title": "B站视频封面：草原旅行视频",
            "source": "B站封面",
        }
    ]


def test_analyze_video_with_qwen_posts_dashscope_compatible_request():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "choices": [
                    {"message": {"content": json.dumps({
                        "summary": "画面呈现草原和户外氛围",
                        "scenes": ["草原远景"],
                        "visual_keywords": ["草原", "松弛感"],
                        "audience_emotion": ["向往"],
                        "usable_facts": ["视频标题提到草原"],
                        "risks": ["不能声称拍摄地为前山牧场"],
                    }, ensure_ascii=False)}}
                ]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    topic = {
        "title": "草原旅行视频",
        "url": "https://www.bilibili.com/video/BVTEST",
        "cover": "https://i0.hdslb.com/bfs/archive/cover.jpg",
        "desc": "一次户外旅行",
        "metrics": {"view": 10000, "like": 888},
    }

    with patch("hotstream.video_analyzer.urlopen", fake_urlopen):
        result = analyze_video_with_qwen(topic=topic, api_key="qwen-key")

    assert captured["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer qwen-key"
    assert captured["body"]["model"] == "qwen2.5-vl-7b-instruct"
    user_content = captured["body"]["messages"][1]["content"]
    assert {part["type"] for part in user_content} == {"image_url", "text"}
    assert "前山牧场四季牧歌" in user_content[-1]["text"]
    assert result["analysis"]["summary"] == "画面呈现草原和户外氛围"
    assert result["raw_text"]
    assert result["images"][0]["source"] == "B站封面"
    assert captured["timeout"] == 60


def test_analyze_video_with_qwen_requires_api_key():
    with pytest.raises(RuntimeError, match="Qwen API Key"):
        analyze_video_with_qwen(topic={"title": "A"}, api_key="")
