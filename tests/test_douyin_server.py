"""Tests for server.py Douyin source normalization and hot-topics routing."""
from __future__ import annotations

import json
from unittest.mock import patch

from hotstream.server import _normalize_source, build_hot_topics_response


# ---------------------------------------------------------------------------
# _normalize_source — douyin aliases
# ---------------------------------------------------------------------------

def test_normalize_source_douyin_key():
    assert _normalize_source("douyin") == "douyin"


def test_normalize_source_douyin_chinese():
    assert _normalize_source("抖音") == "douyin"


def test_normalize_source_douyin_dy_alias():
    assert _normalize_source("dy") == "douyin"


def test_normalize_source_douyin_mixed_case():
    assert _normalize_source("Douyin") == "douyin"


# ---------------------------------------------------------------------------
# build_hot_topics_response — douyin routing
# ---------------------------------------------------------------------------

def test_build_hot_topics_response_douyin_no_keyword():
    """Douyin with no keyword should still call fetch_hot_topics (without keyword)."""
    fake_topics = [
        {
            "rank": 1,
            "title": "草原骑马挑战",
            "source": "抖音",
            "type": "video",
            "hot_value": 980000,
        }
    ]
    with patch("hotstream.server.fetch_hot_topics", return_value=fake_topics) as fetch:
        status, headers, body = build_hot_topics_response(source="douyin", limit=10)

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["success"] is True
    assert payload["source"] == "抖音"
    assert payload["source_key"] == "douyin"
    assert payload["topics"][0]["title"] == "草原骑马挑战"
    fetch.assert_called_once_with("douyin", limit=10, keyword=None, category=None, sort=None)


def test_build_hot_topics_response_douyin_with_keyword():
    """Douyin with keyword should pass keyword through to fetch_hot_topics."""
    with patch("hotstream.server.fetch_hot_topics", return_value=[]) as fetch:
        status, headers, body = build_hot_topics_response(
            source="抖音",
            limit=5,
            keyword="民俗",
        )

    assert status == 200
    fetch.assert_called_once_with("douyin", limit=5, keyword="民俗", category=None, sort=None)


def test_build_hot_topics_response_douyin_alias_dy():
    """'dy' alias should resolve to 'douyin' source_key."""
    with patch("hotstream.server.fetch_hot_topics", return_value=[]) as fetch:
        status, headers, body = build_hot_topics_response(source="dy", limit=3)

    payload = json.loads(body.decode("utf-8"))
    assert payload["source_key"] == "douyin"
    assert payload["source"] == "抖音"
