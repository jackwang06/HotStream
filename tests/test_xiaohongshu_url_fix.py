"""Tests for the Xiaohongshu URL-fix (goal B).

Verifies that parse_xiaohongshu_explore_page (and its helpers) produce URLs
containing the real note id — never collapsing to the bare homepage — when
given synthetic __INITIAL_STATE__ HTML that mimics the live field shapes.

Three key shapes are exercised:
  1. Row-level id + xsecToken  → /explore/{id}?xsec_token=...&xsec_source=pc_feed
  2. Row-level id, no token    → /explore/{id}  (still a real-note URL)
  3. feedsWrapper / placeholderFeeds containers (not just "feeds")
  4. validIds.noteIds fallback when no note cards are renderable
  5. Old noteCard.noteId shape is absent → id comes from row["id"], not noteCard
"""
from __future__ import annotations

import json

import pytest

from hotstream.scraper import (
    _xiaohongshu_feed_rows,
    _xiaohongshu_note_id,
    _xiaohongshu_note_url,
    _xiaohongshu_xsec_token,
    parse_xiaohongshu_explore_page,
)

HOMEPAGE = "https://www.xiaohongshu.com/explore"


# ---------------------------------------------------------------------------
# helper: build synthetic __INITIAL_STATE__ HTML
# ---------------------------------------------------------------------------

def _make_html(state: dict) -> str:
    return (
        "<script>window.__INITIAL_STATE__="
        + json.dumps(state, ensure_ascii=False)
        + ";</script>"
    )


def _make_state(feeds: list | None = None,
                feeds_wrapper: list | None = None,
                placeholder_feeds: list | None = None,
                valid_note_ids: list | None = None) -> dict:
    """Construct a minimal __INITIAL_STATE__ matching the live explore page shape."""
    feed: dict = {}
    if feeds is not None:
        feed["feeds"] = feeds
    if feeds_wrapper is not None:
        feed["feedsWrapper"] = feeds_wrapper
    if placeholder_feeds is not None:
        feed["placeholderFeeds"] = placeholder_feeds
    if valid_note_ids is not None:
        feed["validIds"] = {"noteIds": valid_note_ids}
    return {"feed": feed}


def _make_row(row_id: str, title: str, xsec_token: str = "", liked_count: str = "2.5万") -> dict:
    """Build a feed row with the current live field layout (id at row level)."""
    row: dict = {
        "id": row_id,
        "noteCard": {
            # noteId intentionally absent — matches the live HTML (0 occurrences)
            "displayTitle": title,
            "interactInfo": {"likedCount": liked_count},
        },
    }
    if xsec_token:
        row["xsecToken"] = xsec_token
    return row


# ---------------------------------------------------------------------------
# _xiaohongshu_note_id
# ---------------------------------------------------------------------------

class TestXiaohongshuNoteId:
    def test_returns_row_level_id_first(self):
        row = {"id": "abc123", "noteCard": {"noteId": "old_card_id"}}
        note = row["noteCard"]
        assert _xiaohongshu_note_id(row, note) == "abc123"

    def test_falls_back_to_notecard_noteid(self):
        row = {"noteCard": {"noteId": "card_id_xyz"}}
        note = row["noteCard"]
        assert _xiaohongshu_note_id(row, note) == "card_id_xyz"

    def test_falls_back_to_note_id_snake_case(self):
        row = {}
        note = {"note_id": "snake_id"}
        assert _xiaohongshu_note_id(row, note) == "snake_id"

    def test_returns_empty_string_when_nothing_found(self):
        assert _xiaohongshu_note_id({}, {}) == ""

    def test_skips_null_or_none_values(self):
        row = {"id": None, "noteCard": {"noteId": "real_id"}}
        note = row["noteCard"]
        assert _xiaohongshu_note_id(row, note) == "real_id"


# ---------------------------------------------------------------------------
# _xiaohongshu_xsec_token
# ---------------------------------------------------------------------------

class TestXiaohongshuXsecToken:
    def test_returns_row_level_xsectoken(self):
        row = {"xsecToken": "TOKEN_ABC"}
        assert _xiaohongshu_xsec_token(row, {}) == "TOKEN_ABC"

    def test_returns_snake_case_fallback(self):
        row = {"xsec_token": "SNAKE_TOKEN"}
        assert _xiaohongshu_xsec_token(row, {}) == "SNAKE_TOKEN"

    def test_returns_notecard_token_when_row_missing(self):
        note = {"xsecToken": "CARD_TOKEN"}
        assert _xiaohongshu_xsec_token({}, note) == "CARD_TOKEN"

    def test_returns_empty_string_when_absent(self):
        assert _xiaohongshu_xsec_token({}, {}) == ""


# ---------------------------------------------------------------------------
# _xiaohongshu_note_url
# ---------------------------------------------------------------------------

class TestXiaohongshuNoteUrl:
    def test_with_id_and_token(self):
        url = _xiaohongshu_note_url("abc123", "TOK_XYZ")
        assert url.startswith("https://www.xiaohongshu.com/explore/abc123")
        assert "xsec_token=" in url
        assert "xsec_source=pc_feed" in url
        # Must NOT be the bare homepage.
        assert url != HOMEPAGE

    def test_with_id_no_token(self):
        url = _xiaohongshu_note_url("abc123", "")
        assert url == "https://www.xiaohongshu.com/explore/abc123"
        assert url != HOMEPAGE

    def test_empty_id_returns_homepage(self):
        url = _xiaohongshu_note_url("", "")
        assert url == HOMEPAGE

    def test_token_is_percent_encoded(self):
        url = _xiaohongshu_note_url("id1", "TOK/WITH+SPECIAL=CHARS")
        assert "TOK%2FWITH%2BSPECIAL%3DCHARS" in url


# ---------------------------------------------------------------------------
# parse_xiaohongshu_explore_page — feeds container
# ---------------------------------------------------------------------------

class TestParseXiaohongshuExplorePageFeeds:
    def test_produces_real_note_urls_not_homepage(self):
        rows = [
            _make_row("id_001", "夏日旅行攻略", xsec_token="TK_001"),
            _make_row("id_002", "乡村风光记录", xsec_token="TK_002"),
        ]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) >= 2
        for topic in topics:
            assert topic["url"] != HOMEPAGE
            assert "/explore/" in topic["url"]

    def test_url_contains_real_note_id(self):
        rows = [_make_row("NOTE_REAL_42", "景点推荐", xsec_token="TOKREAL")]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "NOTE_REAL_42" in topics[0]["url"]

    def test_url_contains_xsec_token_when_present(self):
        rows = [_make_row("NID_A", "民俗活动", xsec_token="SECRET_TOKEN")]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "SECRET_TOKEN" in topics[0]["url"]
        assert "xsec_source=pc_feed" in topics[0]["url"]

    def test_url_without_token_still_contains_real_id(self):
        rows = [_make_row("NID_B", "草原牧歌")]  # no xsecToken
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "NID_B" in topics[0]["url"]
        assert topics[0]["url"] != HOMEPAGE

    def test_topic_source_is_xiaohongshu(self):
        rows = [_make_row("NID_C", "旅游笔记")]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert all(t["source"] == "小红书" for t in topics)

    def test_topic_has_title(self):
        rows = [_make_row("NID_D", "露营攻略合集")]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert topics[0]["title"] == "露营攻略合集"

    def test_rows_without_title_are_skipped(self):
        rows = [
            {"id": "no_title_row", "noteCard": {}},
            _make_row("with_title", "有标题"),
        ]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        # Only the row with a title should appear.
        assert len(topics) == 1
        assert topics[0]["title"] == "有标题"

    def test_rows_without_id_are_skipped(self):
        rows = [
            {"noteCard": {"displayTitle": "有标题但无ID"}},
            _make_row("real_id", "有标题有ID"),
        ]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "real_id" in topics[0]["url"]


# ---------------------------------------------------------------------------
# parse_xiaohongshu_explore_page — feedsWrapper / placeholderFeeds containers
# ---------------------------------------------------------------------------

class TestParseXiaohongshuExploreFeedsWrapper:
    def test_feedswrapper_container_yields_real_urls(self):
        rows = [_make_row("WRP_001", "包装容器笔记", xsec_token="TOKWRP")]
        html = _make_html(_make_state(feeds_wrapper=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "WRP_001" in topics[0]["url"]

    def test_placeholderfeeds_container_yields_real_urls(self):
        rows = [_make_row("PH_001", "占位容器笔记", xsec_token="TOKPH")]
        html = _make_html(_make_state(placeholder_feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "PH_001" in topics[0]["url"]

    def test_deduplication_across_containers(self):
        """Same id appearing in feeds + feedsWrapper should count only once."""
        row = _make_row("DUP_ID", "重复笔记", xsec_token="TOKDUP")
        html = _make_html(_make_state(feeds=[row], feeds_wrapper=[row]))
        topics = parse_xiaohongshu_explore_page(html)

        ids = [t["url"] for t in topics if "DUP_ID" in t["url"]]
        assert len(ids) == 1


# ---------------------------------------------------------------------------
# parse_xiaohongshu_explore_page — validIds fallback
# ---------------------------------------------------------------------------

class TestParseXiaohongshuExploreValidIdsFallback:
    def test_validids_fallback_yields_real_note_urls(self):
        """When no note cards render, validIds.noteIds produces /explore/{id} links."""
        state = _make_state(feeds=[], valid_note_ids=["fallback_id_1", "fallback_id_2"])
        html = _make_html(state)
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 2
        for topic in topics:
            assert topic["url"] != HOMEPAGE
            assert "/explore/" in topic["url"]

    def test_validids_fallback_ids_appear_in_urls(self):
        state = _make_state(feeds=[], valid_note_ids=["unique_note_id_xyz"])
        html = _make_html(state)
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "unique_note_id_xyz" in topics[0]["url"]

    def test_validids_fallback_skips_null_entries(self):
        state = _make_state(feeds=[], valid_note_ids=[None, "", "real_id_abc"])
        html = _make_html(state)
        topics = parse_xiaohongshu_explore_page(html)

        assert len(topics) == 1
        assert "real_id_abc" in topics[0]["url"]

    def test_feedscards_take_priority_over_validids(self):
        """If note cards are renderable, validIds fallback must NOT be used."""
        rows = [_make_row("card_id", "笔记卡片")]
        state = _make_state(feeds=rows, valid_note_ids=["fallback_id"])
        html = _make_html(state)
        topics = parse_xiaohongshu_explore_page(html)

        urls = [t["url"] for t in topics]
        assert any("card_id" in u for u in urls)
        assert not any("fallback_id" in u for u in urls)


# ---------------------------------------------------------------------------
# parse_xiaohongshu_explore_page — homepage-URL regression guard
# ---------------------------------------------------------------------------

class TestXiaohongshuHomepageRegression:
    def test_no_topic_url_equals_homepage(self):
        """Regression: every produced URL must be a specific note, not the homepage."""
        rows = [
            _make_row("reg_001", "旅游推荐A", xsec_token="TK1"),
            _make_row("reg_002", "民俗文化B"),
            _make_row("reg_003", "牧场风光C", xsec_token="TK3"),
        ]
        html = _make_html(_make_state(feeds=rows))
        topics = parse_xiaohongshu_explore_page(html)

        for topic in topics:
            assert topic["url"] != HOMEPAGE, (
                f"URL for topic '{topic['title']}' is bare homepage — regression detected"
            )

    def test_empty_state_returns_empty_list_not_homepage_row(self):
        """Empty / no-SSR state must return [] rather than a homepage row."""
        html = _make_html({})
        topics = parse_xiaohongshu_explore_page(html)
        assert topics == []
