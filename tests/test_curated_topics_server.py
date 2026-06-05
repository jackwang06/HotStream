"""Tests for server.build_curated_topics_response (goal A, server layer).

All tests are offline — both fetch_hot_topics and select_relevant_topics are
monkeypatched so no real HTTP is made.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hotstream.server import build_curated_topics_response, CURATED_SOURCES, CURATED_PER_SOURCE_LIMIT

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_SAMPLE_TOPICS_BY_SOURCE = {
    "toutiao": [
        {"title": "头条热点A", "source": "今日头条", "hot_value": 5000},
        {"title": "头条热点B", "source": "今日头条", "hot_value": 4000},
    ],
    "zhihu": [
        {"title": "知乎热点C", "source": "知乎", "hot_value": 3000},
    ],
    "xiaohongshu": [
        {"title": "小红书热点D", "source": "小红书", "hot_value": 2000},
    ],
    "bilibili": [],  # empty — should be silently skipped
    "douyin": [
        {"title": "抖音热点E", "source": "抖音", "hot_value": 1000},
    ],
}

_SELECTED = [
    {"title": "头条热点A", "source": "今日头条", "hot_value": 5000, "reason": "旅游借势"},
    {"title": "知乎热点C", "source": "知乎", "hot_value": 3000, "reason": "文旅相关"},
]


def _raw(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _fetch_side_effect(source, limit):
    return _SAMPLE_TOPICS_BY_SOURCE.get(source, [])


# ---------------------------------------------------------------------------
# missing api_key → 400
# ---------------------------------------------------------------------------

def test_build_curated_topics_no_api_key_returns_400():
    status, _, body = build_curated_topics_response(_raw({"api_key": ""}))
    assert status == 400
    payload = json.loads(body)
    assert payload["success"] is False
    assert "topics" in payload
    assert payload["topics"] == []


def test_build_curated_topics_absent_api_key_returns_400():
    status, _, body = build_curated_topics_response(_raw({}))
    assert status == 400
    payload = json.loads(body)
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# invalid JSON body → 400
# ---------------------------------------------------------------------------

def test_build_curated_topics_invalid_json_returns_400():
    status, _, body = build_curated_topics_response(b"not json{")
    assert status == 400
    payload = json.loads(body)
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# happy path: aggregation + selection + response structure
# ---------------------------------------------------------------------------

def test_build_curated_topics_happy_path_structure():
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        status, headers, body = build_curated_topics_response(
            _raw({"api_key": "sk-test", "knowledge_base": "秋收节活动"})
        )

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body)
    assert payload["success"] is True
    assert "topics" in payload
    assert "updated_at" in payload


def test_build_curated_topics_topics_contain_source_and_reason():
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        _, _, body = build_curated_topics_response(
            _raw({"api_key": "sk-test"})
        )

    payload = json.loads(body)
    for topic in payload["topics"]:
        assert "source" in topic
        assert "reason" in topic
    assert payload["topics"][0]["source"] == "今日头条"
    assert payload["topics"][0]["reason"] == "旅游借势"


def test_build_curated_topics_topics_are_re_ranked_1_to_n():
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        _, _, body = build_curated_topics_response(
            _raw({"api_key": "sk-test"})
        )

    payload = json.loads(body)
    ranks = [t["rank"] for t in payload["topics"]]
    assert ranks == list(range(1, len(_SELECTED) + 1))


def test_build_curated_topics_aggregates_all_five_sources():
    """fetch_hot_topics must be called once per source in CURATED_SOURCES."""
    calls: list[str] = []

    def _tracking_fetch(source, limit):
        calls.append(source)
        return _SAMPLE_TOPICS_BY_SOURCE.get(source, [])

    with patch("hotstream.server.fetch_hot_topics", side_effect=_tracking_fetch), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert set(calls) == set(CURATED_SOURCES)


def test_build_curated_topics_passes_api_key_and_knowledge_base_to_selector():
    """select_relevant_topics must receive the api_key and knowledge_base from the body."""
    captured: dict = {}

    def _fake_select(topics, knowledge_base=None, api_key=None, model=None, api_url=None):
        captured["api_key"] = api_key
        captured["knowledge_base"] = knowledge_base
        return _SELECTED

    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", side_effect=_fake_select):
        build_curated_topics_response(
            _raw({"api_key": "sk-real-key", "knowledge_base": "测试知识库内容"})
        )

    assert captured["api_key"] == "sk-real-key"
    assert captured["knowledge_base"] == "测试知识库内容"


def test_build_curated_topics_skips_source_that_raises():
    """A single failing source should not abort the whole request."""
    fail_count = {"n": 0}

    def _partial_fetch(source, limit):
        if source == "zhihu":
            fail_count["n"] += 1
            raise RuntimeError("知乎抓取超时")
        return _SAMPLE_TOPICS_BY_SOURCE.get(source, [])

    with patch("hotstream.server.fetch_hot_topics", side_effect=_partial_fetch), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        status, _, body = build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert status == 200
    assert fail_count["n"] == 1  # zhihu was tried and skipped


def test_build_curated_topics_all_sources_fail_returns_502():
    """If every source fails, aggregation is empty → 502."""
    with patch("hotstream.server.fetch_hot_topics", side_effect=RuntimeError("全部失败")):
        status, _, body = build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert status == 502
    payload = json.loads(body)
    assert payload["success"] is False


def test_build_curated_topics_select_raises_returns_502():
    """If DeepSeek selection raises, the endpoint must return 502."""
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", side_effect=RuntimeError("DeepSeek error")):
        status, _, body = build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert status == 502
    payload = json.loads(body)
    assert payload["success"] is False
    assert "DeepSeek error" in payload["error"]


def test_build_curated_topics_select_empty_returns_200_empty_list():
    """select_relevant_topics returning [] → success True, empty topics list."""
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", return_value=[]):
        status, _, body = build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert status == 200
    payload = json.loads(body)
    assert payload["success"] is True
    assert payload["topics"] == []


def test_build_curated_topics_content_type_header():
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", return_value=_SELECTED):
        _, headers, _ = build_curated_topics_response(_raw({"api_key": "sk-test"}))

    assert "application/json" in headers["Content-Type"]


def test_build_curated_topics_optional_model_forwarded():
    captured: dict = {}

    def _fake_select(topics, knowledge_base=None, api_key=None, model=None, api_url=None):
        captured["model"] = model
        return []

    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", side_effect=_fake_select):
        build_curated_topics_response(
            _raw({"api_key": "sk-test", "model": "deepseek-reasoner"})
        )

    assert captured["model"] == "deepseek-reasoner"


def test_build_curated_topics_optional_api_url_forwarded():
    captured: dict = {}

    def _fake_select(topics, knowledge_base=None, api_key=None, model=None, api_url=None):
        captured["api_url"] = api_url
        return []

    with patch("hotstream.server.fetch_hot_topics", side_effect=_fetch_side_effect), \
         patch("hotstream.server.select_relevant_topics", side_effect=_fake_select):
        build_curated_topics_response(
            _raw({"api_key": "sk-test", "api_url": "https://custom.api/v1"})
        )

    assert captured["api_url"] == "https://custom.api/v1"
