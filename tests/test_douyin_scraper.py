"""Tests for Douyin hot-search scraper (parse_douyin_hot_search contract)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hotstream.scraper import fetch_hot_topics, parse_douyin_hot_search


# ---------------------------------------------------------------------------
# Minimal fixture — no network calls required
# ---------------------------------------------------------------------------

WORD_LIST_FIXTURE = [
    {
        "word": "草原骑马挑战",
        "hot_value": 980000,
        "word_cover": {"url_list": ["https://p3-sign.douyinpic.com/cover1.jpg"]},
        "sentence_id": 123456,
        "label": "热",
        "video_count": 2000,
        "discuss_video_count": 300,
    },
    {
        "word": "民俗风情园旅游",
        "hot_value": 540000,
        "word_cover": {"url_list": ["https://p3-sign.douyinpic.com/cover2.jpg"]},
        "sentence_id": 0,          # no valid sentence_id → search URL
        "label": "",               # empty → should fall back to hot_value string
        "video_count": 1200,
        "discuss_video_count": 150,
    },
    {
        "word": "新能源汽车评测",
        "hot_value": 1200000,
        "word_cover": {"url_list": []},   # no cover
        "sentence_id": 789,
        "label": "沸",
        "video_count": 5000,
        "discuss_video_count": 800,
    },
]

DOUYIN_PAYLOAD = {
    "status_code": 0,
    "data": {
        "word_list": WORD_LIST_FIXTURE,
    },
}


def _topics():
    return parse_douyin_hot_search(DOUYIN_PAYLOAD)


# ---------------------------------------------------------------------------
# source / type contract
# ---------------------------------------------------------------------------

def test_parse_douyin_all_topics_have_source_douyin():
    topics = _topics()
    assert len(topics) == 3
    for topic in topics:
        assert topic["source"] == "抖音", f"Expected source='抖音', got {topic['source']!r}"


def test_parse_douyin_all_topics_have_type_video():
    topics = _topics()
    for topic in topics:
        assert topic["type"] == "video"


# ---------------------------------------------------------------------------
# title / rank contract
# ---------------------------------------------------------------------------

def test_parse_douyin_titles_match_word_field():
    topics = _topics()
    assert topics[0]["title"] == "草原骑马挑战"
    assert topics[1]["title"] == "民俗风情园旅游"
    assert topics[2]["title"] == "新能源汽车评测"


def test_parse_douyin_ranks_are_sequential_from_one():
    topics = _topics()
    assert [t["rank"] for t in topics] == [1, 2, 3]


# ---------------------------------------------------------------------------
# URL contract
# ---------------------------------------------------------------------------

def test_parse_douyin_url_uses_sentence_id_when_present():
    topics = _topics()
    assert topics[0]["url"] == "https://www.douyin.com/hot/123456"
    assert topics[2]["url"] == "https://www.douyin.com/hot/789"


def test_parse_douyin_url_falls_back_to_search_when_sentence_id_is_zero():
    from urllib.parse import unquote
    topics = _topics()
    # sentence_id == 0 → search URL (word is percent-encoded)
    assert topics[1]["url"].startswith("https://www.douyin.com/search/")
    assert "民俗风情园旅游" in unquote(topics[1]["url"])


# ---------------------------------------------------------------------------
# cover contract
# ---------------------------------------------------------------------------

def test_parse_douyin_cover_taken_from_url_list_first_element():
    topics = _topics()
    assert topics[0]["cover"] == "https://p3-sign.douyinpic.com/cover1.jpg"


def test_parse_douyin_cover_empty_when_url_list_is_empty():
    topics = _topics()
    assert topics[2]["cover"] == ""


# ---------------------------------------------------------------------------
# label contract
# ---------------------------------------------------------------------------

def test_parse_douyin_label_uses_original_when_nonempty():
    topics = _topics()
    assert topics[0]["label"] == "热"
    assert topics[2]["label"] == "沸"


def test_parse_douyin_label_falls_back_to_hot_value_string_when_empty():
    topics = _topics()
    assert topics[1]["label"] == "540000 热度"


# ---------------------------------------------------------------------------
# metrics contract
# ---------------------------------------------------------------------------

def test_parse_douyin_metrics_shape():
    topics = _topics()
    m = topics[0]["metrics"]
    assert m["hot_value"] == 980000
    assert m["video_count"] == 2000
    assert m["discuss_video_count"] == 300


# ---------------------------------------------------------------------------
# hot_value contract
# ---------------------------------------------------------------------------

def test_parse_douyin_hot_value_is_int():
    topics = _topics()
    for topic in topics:
        assert isinstance(topic["hot_value"], int)


# ---------------------------------------------------------------------------
# fetch_hot_topics dispatch for "douyin"
# ---------------------------------------------------------------------------

def test_fetch_hot_topics_dispatches_douyin():
    # fetch_hot_topics over-fetches (limit=FETCH_ALL_LIMIT) then truncates; the
    # underlying fetch_douyin_hot_topics receives the large internal limit.
    from hotstream.scraper import FETCH_ALL_LIMIT
    with patch("hotstream.scraper.fetch_douyin_hot_topics", return_value=[{"title": "D", "source": "抖音"}]) as fetch:
        result = fetch_hot_topics("douyin", limit=1)
    assert result[0]["title"] == "D"
    fetch.assert_called_once_with(limit=FETCH_ALL_LIMIT, timeout=10, keyword=None)


def test_fetch_hot_topics_dispatches_douyin_alias_dy():
    with patch("hotstream.scraper.fetch_douyin_hot_topics", return_value=[]) as fetch:
        fetch_hot_topics("dy", limit=5)
    fetch.assert_called_once()


def test_fetch_hot_topics_dispatches_douyin_chinese_alias():
    with patch("hotstream.scraper.fetch_douyin_hot_topics", return_value=[]) as fetch:
        fetch_hot_topics("抖音", limit=5)
    fetch.assert_called_once()
