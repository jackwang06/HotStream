"""Tests for copywriter.select_relevant_topics (curated-topics feature, goal A).

All tests are offline — network calls are monkeypatched so no real HTTP is made.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hotstream.copywriter import (
    CURATED_TOPICS_MAX,
    _build_selection_messages,
    _extract_selection_object,
    select_relevant_topics,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

FAKE_TOPICS = [
    {"title": "夏日露营热潮", "source": "今日头条", "hot_value": 9000},
    {"title": "乡村旅游政策", "source": "知乎", "hot_value": 8000},
    {"title": "明星出轨风波", "source": "抖音", "hot_value": 70000},
]


def _make_deepseek_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


class _FakeResponse:
    def __init__(self, content: str):
        self._data = json.dumps(_make_deepseek_response(content)).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._data


# ---------------------------------------------------------------------------
# _extract_selection_object
# ---------------------------------------------------------------------------

def test_extract_selection_object_parses_plain_json():
    raw = '{"selected":[{"index":1,"reason":"契合乡村"}]}'
    result = _extract_selection_object(raw)
    assert result == {"selected": [{"index": 1, "reason": "契合乡村"}]}


def test_extract_selection_object_strips_markdown_fences():
    raw = '```json\n{"selected":[{"index":2,"reason":"旅游相关"}]}\n```'
    result = _extract_selection_object(raw)
    assert result == {"selected": [{"index": 2, "reason": "旅游相关"}]}


def test_extract_selection_object_extracts_outermost_braces():
    # Model output with extra prose before/after the JSON object.
    raw = '这是我的选择结果：\n{"selected":[{"index":1,"reason":"露营"}]}\n好的。'
    result = _extract_selection_object(raw)
    assert isinstance(result, dict)
    assert "selected" in result


def test_extract_selection_object_returns_none_on_empty():
    assert _extract_selection_object("") is None
    assert _extract_selection_object("  ") is None


def test_extract_selection_object_returns_none_on_invalid():
    assert _extract_selection_object("not json at all") is None
    assert _extract_selection_object("{bad json}") is None


def test_extract_selection_object_returns_none_on_non_dict():
    # A JSON array is not the expected shape.
    result = _extract_selection_object("[1,2,3]")
    assert result is None


# ---------------------------------------------------------------------------
# _build_selection_messages
# ---------------------------------------------------------------------------

def test_build_selection_messages_structure():
    msgs = _build_selection_messages(FAKE_TOPICS)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_build_selection_messages_system_mentions_venue():
    msgs = _build_selection_messages(FAKE_TOPICS)
    assert "前山牧场四季牧歌民俗风情园" in msgs[0]["content"]


def test_build_selection_messages_user_lists_numbered_topics():
    msgs = _build_selection_messages(FAKE_TOPICS)
    user = msgs[1]["content"]
    assert "1. [今日头条] 夏日露营热潮" in user
    assert "2. [知乎] 乡村旅游政策" in user
    assert "3. [抖音] 明星出轨风波" in user


def test_build_selection_messages_includes_knowledge_base_when_provided():
    msgs = _build_selection_messages(FAKE_TOPICS, knowledge_base="即将举办烧烤节活动")
    user = msgs[1]["content"]
    assert "知识库参考资料" in user
    assert "烧烤节" in user


def test_build_selection_messages_omits_knowledge_section_when_empty():
    msgs = _build_selection_messages(FAKE_TOPICS, knowledge_base=None)
    user = msgs[1]["content"]
    assert "知识库参考资料" not in user


def test_build_selection_messages_mentions_max_count():
    msgs = _build_selection_messages(FAKE_TOPICS)
    assert str(CURATED_TOPICS_MAX) in msgs[1]["content"]


def test_build_selection_messages_instructs_json_output():
    msgs = _build_selection_messages(FAKE_TOPICS)
    user = msgs[1]["content"]
    assert "selected" in user
    assert "index" in user
    assert "reason" in user


# ---------------------------------------------------------------------------
# select_relevant_topics — happy path (monkeypatched)
# ---------------------------------------------------------------------------

def test_select_relevant_topics_returns_mapped_topics_with_reason():
    deepseek_json = json.dumps(
        {"selected": [{"index": 1, "reason": "露营旅游契合"}, {"index": 2, "reason": "乡村政策借势"}]}
    )

    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            knowledge_base="",
            api_key="test-key",
        )

    assert len(result) == 2
    assert result[0]["title"] == "夏日露营热潮"
    assert result[0]["source"] == "今日头条"
    assert result[0]["reason"] == "露营旅游契合"
    assert result[1]["title"] == "乡村旅游政策"
    assert result[1]["reason"] == "乡村政策借势"


def test_select_relevant_topics_source_preserved_on_every_result():
    deepseek_json = json.dumps(
        {"selected": [{"index": 2, "reason": "政策热点"}]}
    )

    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            knowledge_base="",
            api_key="test-key",
        )

    assert result[0]["source"] == "知乎"


def test_select_relevant_topics_skips_out_of_range_indices():
    # index 99 does not exist in FAKE_TOPICS (length 3)
    deepseek_json = json.dumps(
        {"selected": [{"index": 99, "reason": "越界"}, {"index": 1, "reason": "有效"}]}
    )

    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            knowledge_base="",
            api_key="test-key",
        )

    assert len(result) == 1
    assert result[0]["title"] == "夏日露营热潮"


def test_select_relevant_topics_skips_duplicate_indices():
    deepseek_json = json.dumps(
        {"selected": [{"index": 1, "reason": "首选"}, {"index": 1, "reason": "重复"}]}
    )

    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            knowledge_base="",
            api_key="test-key",
        )

    assert len(result) == 1


def test_select_relevant_topics_respects_curated_max():
    # Build a pool of 20 topics.
    big_topics = [{"title": f"热点{i}", "source": "今日头条"} for i in range(1, 21)]
    # DeepSeek returns 15 — more than CURATED_TOPICS_MAX (12).
    selected = [{"index": i, "reason": f"理由{i}"} for i in range(1, 16)]
    deepseek_json = json.dumps({"selected": selected})

    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            big_topics,
            api_key="test-key",
        )

    assert len(result) <= CURATED_TOPICS_MAX


# ---------------------------------------------------------------------------
# select_relevant_topics — failure / edge cases
# ---------------------------------------------------------------------------

def test_select_relevant_topics_returns_empty_list_on_parse_failure():
    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse("完全无法解析的回复")):
        result = select_relevant_topics(
            FAKE_TOPICS,
            api_key="test-key",
        )

    assert result == []


def test_select_relevant_topics_returns_empty_list_on_empty_selected():
    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse('{"selected":[]}')):
        result = select_relevant_topics(
            FAKE_TOPICS,
            api_key="test-key",
        )

    assert result == []


def test_select_relevant_topics_returns_empty_list_for_empty_input():
    # No HTTP call should be made, and function returns [] immediately.
    result = select_relevant_topics([], api_key="test-key")
    assert result == []


def test_select_relevant_topics_raises_on_missing_api_key():
    with patch("hotstream.copywriter.load_project_env", lambda: None):
        with pytest.raises(RuntimeError, match="API Key"):
            select_relevant_topics(FAKE_TOPICS, api_key="")


def test_select_relevant_topics_markdown_fenced_json_is_parsed():
    """Model wraps output in ```json ... ``` — must still be decoded."""
    fenced = '```json\n{"selected":[{"index":3,"reason":"娱乐热点无关"}]}\n```'
    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(fenced)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            api_key="test-key",
        )

    assert len(result) == 1
    assert result[0]["title"] == "明星出轨风波"
    assert result[0]["reason"] == "娱乐热点无关"


def test_select_relevant_topics_reason_omitted_when_empty():
    deepseek_json = json.dumps({"selected": [{"index": 1, "reason": ""}]})
    with patch("hotstream.copywriter.urlopen", return_value=_FakeResponse(deepseek_json)):
        result = select_relevant_topics(
            FAKE_TOPICS,
            api_key="test-key",
        )

    # Empty reason string is not attached to the topic dict.
    assert "reason" not in result[0]


def test_select_relevant_topics_passes_knowledge_base_in_messages():
    """knowledge_base text must surface inside the DeepSeek request body."""
    captured: dict = {}
    deepseek_json = json.dumps({"selected": [{"index": 1, "reason": "ok"}]})

    class _Cap(_FakeResponse):
        def __init__(self):
            super().__init__(deepseek_json)

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Cap()

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        select_relevant_topics(
            FAKE_TOPICS,
            knowledge_base="秋收音乐节将于十月举办",
            api_key="test-key",
        )

    user_content = captured["body"]["messages"][1]["content"]
    assert "秋收音乐节" in user_content
