import json
from unittest.mock import patch

import pytest

from hotstream.video_analyzer import (
    _build_qwen_messages,
    analyze_video_with_qwen,
    build_video_materials,
)


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


def test_build_video_materials_douyin_source_label():
    topic = {
        "title": "抖音热点视频",
        "cover": "https://p3-sign.douyinpic.com/cover.jpg",
        "source": "抖音",
    }

    materials = build_video_materials(topic)

    assert len(materials) == 1
    assert materials[0]["title"] == "抖音视频封面：抖音热点视频"
    assert materials[0]["source"] == "抖音封面"
    assert materials[0]["url"] == "https://p3-sign.douyinpic.com/cover.jpg"


def test_build_qwen_messages_bilibili_topic_contains_bilibili_not_douyin():
    topic = {
        "title": "B站热门",
        "url": "https://www.bilibili.com/video/BVTEST",
        "cover": "https://i0.hdslb.com/cover.jpg",
        "source": "B站",
    }

    messages = _build_qwen_messages(topic)
    user_text = messages[1]["content"][-1]["text"]

    assert "B站" in user_text
    assert "抖音" not in user_text


def test_build_qwen_messages_douyin_topic_contains_douyin_not_bilibili():
    topic = {
        "title": "草原骑马挑战",
        "url": "https://www.douyin.com/hot/123456",
        "cover": "https://p3-sign.douyinpic.com/cover.jpg",
        "source": "抖音",
        "metrics": {"hot_value": 980000, "video_count": 2000, "discuss_video_count": 300},
    }

    messages = _build_qwen_messages(topic)
    user_text = messages[1]["content"][-1]["text"]

    assert "抖音" in user_text
    assert "B站" not in user_text


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
    assert captured["body"]["model"] == "qwen-vl-max"
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
