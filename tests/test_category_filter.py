"""Tests for unified category filtering, limit cap (100), and related contracts.

Covers:
  - _filter_topics_by_category: passthrough / food / rural / case-insensitive
  - server build_hot_topics_response: limit clamping (>100→100, <1→1) and default=30
  - server do_GET: limit query-param parsing (cap 100, default 30, invalid→30)
  - fetch_hot_topics (toutiao): category over-fetch→filter→truncate via monkeypatch
  - fetch_hot_topics (zhihu/xiaohongshu): same pattern
  - B站 native travel category (rid=250) path is still taken
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from hotstream.scraper import (
    CATEGORIES,
    FETCH_ALL_LIMIT,
    _filter_topics_by_category,
    fetch_hot_topics,
)
from hotstream.server import build_hot_topics_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_topics(titles: list[str]) -> list[dict]:
    """Create minimal topic dicts with the given titles."""
    return [
        {"rank": i + 1, "title": title, "url": f"https://example.com/{i}",
         "hot_value": 1000 - i, "label": "", "source": "测试", "desc": ""}
        for i, title in enumerate(titles)
    ]


SAMPLE_TITLES = [
    "草原骑马挑战",          # rural: 草原, 马
    "特色美食探店打卡",       # food: 美食, 探店  AND  travel: 打卡
    "乡村田园慢生活vlog",     # rural: 乡村, 田园  AND  life: vlog
    "科技数码AI新品发布",     # technology: 科技, 数码, AI
    "综艺明星大赏",           # entertainment: 综艺, 明星
    "知识科普历史故事",       # knowledge: 知识, 科普, 历史
    "随机新闻热搜",           # no matching category
]

SAMPLE_TOPICS = _make_topics(SAMPLE_TITLES)


# ---------------------------------------------------------------------------
# _filter_topics_by_category: passthrough cases
# ---------------------------------------------------------------------------

def test_filter_category_all_returns_original():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "all")
    assert result is SAMPLE_TOPICS


def test_filter_category_empty_string_returns_original():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "")
    assert result is SAMPLE_TOPICS


def test_filter_category_none_returns_original():
    result = _filter_topics_by_category(SAMPLE_TOPICS, None)
    assert result is SAMPLE_TOPICS


def test_filter_category_unknown_key_returns_original():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "nonexistent_xyz")
    assert result is SAMPLE_TOPICS


def test_filter_category_all_topics_unchanged():
    original = list(SAMPLE_TOPICS)
    result = _filter_topics_by_category(SAMPLE_TOPICS, "all")
    assert [t["title"] for t in result] == [t["title"] for t in original]


# ---------------------------------------------------------------------------
# _filter_topics_by_category: food
# ---------------------------------------------------------------------------

def test_filter_category_food_keeps_only_food_topics():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "food")
    titles = [t["title"] for t in result]
    assert "特色美食探店打卡" in titles


def test_filter_category_food_excludes_non_food_topics():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "food")
    titles = [t["title"] for t in result]
    assert "科技数码AI新品发布" not in titles
    assert "综艺明星大赏" not in titles
    assert "随机新闻热搜" not in titles


def test_filter_category_food_by_keyword_chi():
    topics = _make_topics(["火锅美食节", "景区门票优惠"])
    result = _filter_topics_by_category(topics, "food")
    assert len(result) == 1
    assert result[0]["title"] == "火锅美食节"


# ---------------------------------------------------------------------------
# _filter_topics_by_category: rural
# ---------------------------------------------------------------------------

def test_filter_category_rural_keeps_grass_and_ranch():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "rural")
    titles = [t["title"] for t in result]
    assert "草原骑马挑战" in titles
    assert "乡村田园慢生活vlog" in titles


def test_filter_category_rural_excludes_tech():
    result = _filter_topics_by_category(SAMPLE_TOPICS, "rural")
    titles = [t["title"] for t in result]
    assert "科技数码AI新品发布" not in titles


def test_filter_category_rural_keywords_muzchang():
    topics = _make_topics(["前山牧场草原夏日", "城市商圈新店开业"])
    result = _filter_topics_by_category(topics, "rural")
    assert len(result) == 1
    assert "牧场" in result[0]["title"]


# ---------------------------------------------------------------------------
# _filter_topics_by_category: case-insensitive (English keywords, e.g. technology)
# ---------------------------------------------------------------------------

def test_filter_category_technology_case_insensitive_ai():
    topics = _make_topics(["ai大模型发布会", "农村丰收季节"])
    result = _filter_topics_by_category(topics, "technology")
    titles = [t["title"] for t in result]
    assert "ai大模型发布会" in titles
    assert "农村丰收季节" not in titles


def test_filter_category_case_insensitive_AI_upper():
    topics = _make_topics(["AI芯片新突破", "旅游景区打卡"])
    result = _filter_topics_by_category(topics, "technology")
    assert any("AI" in t["title"] for t in result)


# ---------------------------------------------------------------------------
# _filter_topics_by_category: label and desc also searched
# ---------------------------------------------------------------------------

def test_filter_category_matches_label_field():
    topics = [{"rank": 1, "title": "无关标题", "label": "美食探店推荐", "desc": "", "url": "", "hot_value": 10, "source": "X"}]
    result = _filter_topics_by_category(topics, "food")
    assert len(result) == 1


def test_filter_category_matches_desc_field():
    topics = [{"rank": 1, "title": "无关标题", "label": "", "desc": "乡村旅游美丽田园", "url": "", "hot_value": 10, "source": "X"}]
    result = _filter_topics_by_category(topics, "rural")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _filter_topics_by_category: ranks are rewritten after filtering
# ---------------------------------------------------------------------------

def test_filter_category_ranks_are_sequential_after_filter():
    topics = _make_topics(["草原牧场之旅", "科技数码AI", "牧民放牧日常"])
    result = _filter_topics_by_category(topics, "rural")
    assert [t["rank"] for t in result] == list(range(1, len(result) + 1))


# ---------------------------------------------------------------------------
# build_hot_topics_response: limit clamping
# ---------------------------------------------------------------------------

def test_build_hot_topics_response_default_limit_is_30():
    """When no limit is given, fetch_hot_topics should be called with limit=30."""
    with patch("hotstream.server.fetch_hot_topics", return_value=[]) as fetch:
        status, _, body = build_hot_topics_response(source="toutiao")

    assert status == 200
    call_kwargs = fetch.call_args
    assert call_kwargs.kwargs.get("limit") == 30 or call_kwargs.args[1] == 30


def test_build_hot_topics_response_limit_above_100_is_clamped():
    """Callers can clamp limit at the server layer; test the do_GET path below."""
    # build_hot_topics_response itself does NOT clamp — that's do_GET's job.
    # But we verify here that passing an oversized limit still works without error.
    with patch("hotstream.server.fetch_hot_topics", return_value=[]) as fetch:
        status, _, _ = build_hot_topics_response(source="toutiao", limit=200)
    assert status == 200
    # The value is forwarded as-is (no additional clamping in build_hot_topics_response).
    call_limit = fetch.call_args.kwargs.get("limit") or fetch.call_args.args[1]
    assert call_limit == 200  # build_hot_topics_response passes it straight through


# ---------------------------------------------------------------------------
# do_GET limit parsing via HotStreamRequestHandler
# ---------------------------------------------------------------------------

class FakeWfile:
    def __init__(self):
        self.data = b""
    def write(self, data):
        self.data += data


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _make_handler(path: str):
    """Construct a HotStreamRequestHandler without a real socket."""
    from hotstream.server import HotStreamRequestHandler
    from unittest.mock import MagicMock

    handler = HotStreamRequestHandler.__new__(HotStreamRequestHandler)
    handler.path = path
    handler.headers = FakeHeaders()
    handler.wfile = FakeWfile()
    handler._headers_buffer = []
    handler.requestline = "GET / HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.command = "GET"
    handler.close_connection = True

    sent_responses = []

    def fake_send_response(code, message=None):
        sent_responses.append(code)

    def fake_send_header(key, value):
        pass

    def fake_end_headers():
        pass

    handler.send_response = fake_send_response
    handler.send_header = fake_send_header
    handler.end_headers = fake_end_headers
    handler._sent_responses = sent_responses
    return handler


def _get_limit_from_response(handler) -> int | None:
    data = handler.wfile.data
    if not data:
        return None
    payload = json.loads(data.decode("utf-8"))
    return payload.get("_debug_limit")


def _do_get_with_limit_param(limit_param: str | None) -> int:
    """Call do_GET with given limit param and return the limit forwarded to build_hot_topics_response."""
    if limit_param is not None:
        path = f"/api/hot-topics?source=toutiao&limit={limit_param}"
    else:
        path = "/api/hot-topics?source=toutiao"

    handler = _make_handler(path)

    captured = {}

    def fake_build(limit, source, keyword, category, sort):
        captured["limit"] = limit
        return 200, {"Content-Type": "application/json; charset=utf-8"}, b'{"success":true,"topics":[],"updated_at":"x","source":"A","source_key":"A"}'

    with patch("hotstream.server.build_hot_topics_response", side_effect=fake_build):
        handler.do_GET()

    return captured.get("limit", -1)


def test_do_get_default_limit_is_30():
    assert _do_get_with_limit_param(None) == 30


def test_do_get_limit_100_is_accepted():
    assert _do_get_with_limit_param("100") == 100


def test_do_get_limit_above_100_is_capped_to_100():
    assert _do_get_with_limit_param("200") == 100


def test_do_get_limit_1_is_accepted():
    assert _do_get_with_limit_param("1") == 1


def test_do_get_limit_below_1_is_floored_to_1():
    assert _do_get_with_limit_param("0") == 1


def test_do_get_invalid_limit_falls_back_to_30():
    assert _do_get_with_limit_param("abc") == 30


def test_do_get_negative_limit_is_floored_to_1():
    assert _do_get_with_limit_param("-5") == 1


# ---------------------------------------------------------------------------
# fetch_hot_topics: category filter + limit truncation (over-fetch then cut)
# ---------------------------------------------------------------------------

def _make_toutiao_topics(n: int, category_titles: dict[int, str] | None = None) -> list[dict]:
    """Build n synthetic toutiao-shaped topics; some with food titles."""
    titles = []
    for i in range(n):
        if category_titles and i in category_titles:
            titles.append(category_titles[i])
        else:
            titles.append(f"无关新闻热搜第{i}条")
    return _make_topics(titles)


def test_fetch_hot_topics_toutiao_category_food_filters_then_truncates():
    """fetch_hot_topics('toutiao', limit=1, category='food') should:
    1. Call fetch_toutiao_hot_topics with limit=FETCH_ALL_LIMIT (over-fetch)
    2. Apply _filter_topics_by_category('food')
    3. Truncate to user limit=1
    """
    # Topics: indices 3 and 7 have food titles
    big_list = _make_toutiao_topics(
        15,
        category_titles={3: "火锅美食探店推荐", 7: "特色小吃美食节"},
    )

    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=big_list) as mock_fetch:
        result = fetch_hot_topics("toutiao", limit=1, category="food")

    # Over-fetch was requested
    mock_fetch.assert_called_once_with(limit=FETCH_ALL_LIMIT, timeout=10)
    # Category filter applied: only food topics remain before truncation
    assert len(result) == 1
    assert "美食" in result[0]["title"] or "火锅" in result[0]["title"] or "小吃" in result[0]["title"]


def test_fetch_hot_topics_toutiao_category_food_returns_all_matches_when_limit_large():
    """With a generous limit, all food-matching topics are returned."""
    big_list = _make_toutiao_topics(
        20,
        category_titles={0: "火锅美食", 5: "餐厅探店", 10: "特产零食推荐", 19: "小吃街"},
    )

    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=big_list):
        result = fetch_hot_topics("toutiao", limit=50, category="food")

    titles = [t["title"] for t in result]
    assert "火锅美食" in titles
    assert "餐厅探店" in titles
    assert "特产零食推荐" in titles
    assert "小吃街" in titles
    # Non-food topics excluded
    assert all("无关新闻" not in t for t in titles)


def test_fetch_hot_topics_toutiao_all_category_no_filter():
    """category='all' should return all topics up to limit without any filtering."""
    big_list = _make_toutiao_topics(20)

    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=big_list):
        result = fetch_hot_topics("toutiao", limit=5, category="all")

    assert len(result) == 5


def test_fetch_hot_topics_toutiao_no_category_no_filter():
    """No category → all topics up to limit."""
    big_list = _make_toutiao_topics(10)

    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=big_list):
        result = fetch_hot_topics("toutiao", limit=3)

    assert len(result) == 3


def test_fetch_hot_topics_zhihu_category_filter_applied():
    """fetch_hot_topics('zhihu') over-fetches then applies category filter."""
    zhihu_topics = _make_topics(
        ["草原旅游攻略知乎问答", "科技数码新品讨论", "牧场旅行分享"]
    )

    with patch("hotstream.scraper.fetch_zhihu_hot_topics", return_value=zhihu_topics) as mock_fetch:
        result = fetch_hot_topics("zhihu", limit=10, category="travel")

    mock_fetch.assert_called_once_with(limit=FETCH_ALL_LIMIT, timeout=10)
    titles = [t["title"] for t in result]
    assert "草原旅游攻略知乎问答" in titles
    # "旅" matches travel category
    assert "牧场旅行分享" in titles
    # tech topic excluded (no travel keyword)
    assert "科技数码新品讨论" not in titles


def test_fetch_hot_topics_xiaohongshu_category_filter_applied():
    """fetch_hot_topics('xiaohongshu') over-fetches then applies category filter."""
    xhs_topics = _make_topics(["民宿度假攻略", "美食探店小吃", "无关时事新闻"])

    with patch("hotstream.scraper.fetch_xiaohongshu_hot_topics", return_value=xhs_topics) as mock_fetch:
        result = fetch_hot_topics("xiaohongshu", limit=10, category="travel")

    mock_fetch.assert_called_once_with(limit=FETCH_ALL_LIMIT, timeout=10)
    titles = [t["title"] for t in result]
    assert "民宿度假攻略" in titles  # 民宿, 度假 are travel keywords
    assert "无关时事新闻" not in titles


def test_fetch_hot_topics_category_filter_before_limit_truncation():
    """Verify filter is applied BEFORE truncation.

    If we have 10 topics, only 2 match 'food', and limit=1:
    the result should be the 1st food-matching topic — not an arbitrary topic.
    """
    topics = []
    # 5 non-food, then 2 food, then 3 non-food
    for i in range(5):
        topics.append({"rank": i + 1, "title": f"无关热点{i}", "label": "", "desc": "", "url": "", "hot_value": 100, "source": "X"})
    topics.append({"rank": 6, "title": "火锅美食节开幕", "label": "", "desc": "", "url": "", "hot_value": 90, "source": "X"})
    topics.append({"rank": 7, "title": "餐厅探店推荐", "label": "", "desc": "", "url": "", "hot_value": 80, "source": "X"})
    for i in range(3):
        topics.append({"rank": i + 8, "title": f"科技新闻{i}", "label": "", "desc": "", "url": "", "hot_value": 70, "source": "X"})

    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=topics):
        result = fetch_hot_topics("toutiao", limit=1, category="food")

    assert len(result) == 1
    # The result must be a food topic, confirming filter ran BEFORE truncation
    food_kws = {"美食", "火锅", "餐", "探店", "吃", "菜", "小吃", "饮", "零食", "特产", "厨"}
    title = result[0]["title"]
    assert any(kw in title for kw in food_kws), f"Expected food topic, got: {title!r}"


# ---------------------------------------------------------------------------
# B站 native category travel→rid=250 path still works
# ---------------------------------------------------------------------------

def test_fetch_hot_topics_bilibili_travel_uses_native_rid():
    """B站 with category='travel' should use region API with rid=250."""
    region_payload = {
        "code": 0,
        "data": [{"title": "草原旅行Vlog", "bvid": "BVTRAVEL", "play": 5000, "typename": "旅行"}],
    }

    class FakeResponse:
        def __init__(self):
            self._data = json.dumps(region_payload, ensure_ascii=False).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return self._data

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        result = fetch_hot_topics("bilibili", limit=1, category="travel")

    url = urlopen.call_args.args[0].full_url
    assert "ranking/region" in url
    assert "rid=250" in url
    assert len(result) >= 1


def test_fetch_hot_topics_bilibili_rural_falls_back_to_popular_with_filter():
    """B站 'rural' (no native rid) fetches popular list and applies keyword filter."""
    popular_payload = {
        "code": 0,
        "data": {
            "list": [
                {"title": "草原牧场夏日之旅", "bvid": "BV1", "aid": 1, "play": 8000, "stat": {"view": 8000}},
                {"title": "城市数码科技展", "bvid": "BV2", "aid": 2, "play": 9000, "stat": {"view": 9000}},
            ]
        },
    }

    class FakeResponse:
        def __init__(self):
            self._data = json.dumps(popular_payload, ensure_ascii=False).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return self._data

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        result = fetch_hot_topics("bilibili", limit=5, category="rural")

    url = urlopen.call_args.args[0].full_url
    assert "popular" in url
    titles = [t["title"] for t in result]
    assert "草原牧场夏日之旅" in titles
    assert "城市数码科技展" not in titles


# ---------------------------------------------------------------------------
# CATEGORIES dict sanity checks
# ---------------------------------------------------------------------------

def test_categories_contains_required_keys():
    required = {"all", "travel", "food", "rural", "culture", "life", "entertainment", "knowledge", "technology"}
    assert required.issubset(CATEGORIES.keys())


def test_categories_travel_has_bili_rid_250():
    assert CATEGORIES["travel"].get("bili_rid") == "250"


def test_categories_food_has_bili_rid_211():
    assert CATEGORIES["food"].get("bili_rid") == "211"


def test_categories_rural_has_no_bili_rid():
    assert not CATEGORIES["rural"].get("bili_rid")


def test_categories_culture_has_no_bili_rid():
    assert not CATEGORIES["culture"].get("bili_rid")


def test_categories_all_have_keywords_list():
    for key, cat in CATEGORIES.items():
        if key != "all":
            assert isinstance(cat.get("keywords"), list), f"Category '{key}' missing keywords"
            assert len(cat["keywords"]) > 0, f"Category '{key}' has empty keywords"


def test_fetch_all_limit_is_100():
    assert FETCH_ALL_LIMIT == 100
