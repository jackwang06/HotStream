import json
from unittest.mock import patch

import pytest

from hotstream.copywriter import (
    DEFAULT_GLOBAL_PROMPT,
    build_default_temporary_prompt,
    build_deepseek_messages,
    generate_copy_with_deepseek,
)


def test_build_deepseek_messages_includes_topic_and_user_brief():
    topic = {"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345}

    messages = build_deepseek_messages(topic=topic, brief="适合公众号，300 字以内")

    assert messages[0]["role"] == "system"
    assert "资深中文新媒体文案" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "AI 应用爆发" in messages[1]["content"]
    assert "适合公众号，300 字以内" in messages[1]["content"]
    assert "前山牧场四季牧歌民俗风情园" in messages[1]["content"]
    assert "平均海拔约 2400 米" in messages[1]["content"]


def test_build_deepseek_messages_asks_for_finished_post_not_writing_advice():
    messages = build_deepseek_messages(
        topic={"title": "赵文卓现身闽超，再现郑成功经典形象", "source": "今日头条", "hot_value": 27610664},
        brief="适合小红书/公众号开头，语气简洁、有信息量。",
    )

    prompt = messages[0]["content"] + "\n" + messages[1]["content"]

    assert "直接输出一篇已经写好的推文正文" in prompt
    assert "不要输出写作建议" in prompt
    assert "不要输出可选角度" in prompt
    assert "禁止编造" in prompt
    assert "不要添加服装、动作、现场反应" in prompt
    assert "以热点标题和补充信息能确认的事实为边界" in prompt
    assert "输出格式" in prompt
    assert "开头" in prompt
    assert "正文" in prompt
    assert "结尾" in prompt


def test_build_deepseek_messages_allows_global_and_temporary_prompt_overrides():
    topic = {"title": "AI 应用爆发", "source": "知乎", "hot_value": 12345}

    messages = build_deepseek_messages(
        topic=topic,
        brief="补充要求",
        global_prompt="你是犀利短评作者。",
        temporary_prompt="只写 3 句话，第一句话必须有冲突感。",
    )

    assert messages == [
        {"role": "system", "content": "你是犀利短评作者。"},
        {"role": "user", "content": "只写 3 句话，第一句话必须有冲突感。"},
    ]


def test_build_default_temporary_prompt_contains_topic_and_user_brief():
    prompt = build_default_temporary_prompt(
        topic={"title": "AI 应用爆发", "source": "知乎", "hot_value": 12345, "label": "讨论升温"},
        brief="公众号，300 字以内",
    )

    assert "AI 应用爆发" in prompt
    assert "知乎" in prompt
    assert "12345" in prompt
    assert "讨论升温" in prompt
    assert "公众号，300 字以内" in prompt
    assert "前山牧场四季牧歌民俗风情园" in prompt
    assert "所有生成推文必须服务于" in prompt


def test_build_default_temporary_prompt_includes_qwen_video_analysis_for_bilibili():
    prompt = build_default_temporary_prompt(
        topic={"title": "草原旅行视频", "source": "B站", "url": "https://www.bilibili.com/video/BVTEST"},
        brief="写成推广推文",
        qwen_analysis={
            "summary": "视频呈现开阔草原和户外松弛感",
            "visual_keywords": ["草原", "星空"],
            "usable_facts": ["视频标题提到草原旅行"],
            "risks": ["不能声称视频拍摄地为前山牧场"],
        },
    )

    assert "Qwen2.5-VL 视频分析" in prompt
    assert "视频呈现开阔草原和户外松弛感" in prompt
    assert "草原" in prompt
    assert "不能声称视频拍摄地为前山牧场" in prompt
    assert "前山牧场四季牧歌" in prompt
    assert "不要编造" in prompt


def test_default_global_prompt_is_exposed_for_ui_editing():
    assert "资深中文新媒体文案" in DEFAULT_GLOBAL_PROMPT
    assert "不是写作顾问" in DEFAULT_GLOBAL_PROMPT


def test_generate_copy_with_deepseek_posts_chat_completion_request():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "choices": [
                    {"message": {"content": "这是 DeepSeek 生成的热点文案。"}}
                ]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        result = generate_copy_with_deepseek(
            topic={"title": "AI 应用爆发", "source": "今日头条", "hot_value": 12345},
            brief="写得简洁一点",
            api_key="test-key",
        )

    assert result == "这是 DeepSeek 生成的热点文案。"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-chat"
    assert captured["body"]["messages"][1]["content"].find("AI 应用爆发") >= 0
    assert captured["timeout"] == 45


def test_generate_copy_with_deepseek_uses_prompt_overrides_in_request_body():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "生成结果"}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        generate_copy_with_deepseek(
            topic={"title": "AI 应用爆发"},
            brief="",
            api_key="test-key",
            global_prompt="全局设定",
            temporary_prompt="临时提示词",
        )

    assert captured["body"]["messages"] == [
        {"role": "system", "content": "全局设定"},
        {"role": "user", "content": "临时提示词"},
    ]


def test_generate_copy_with_deepseek_requires_api_key():
    with patch("hotstream.copywriter.load_project_env", lambda: None), patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="DeepSeek API Key"):
            generate_copy_with_deepseek(topic={"title": "A"}, brief="", api_key="")


def test_generate_copy_with_deepseek_does_not_fallback_to_env_api_key():
    with patch("hotstream.copywriter.load_project_env", lambda: None), patch.dict("os.environ", {"DEEPSEEK_API_KEY": "env-key"}, clear=True):
        with pytest.raises(RuntimeError, match="DeepSeek API Key"):
            generate_copy_with_deepseek(topic={"title": "A"}, brief="")
