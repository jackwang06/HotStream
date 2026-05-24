import json
from unittest.mock import patch

import pytest

from hotstream.scraper import (
    fetch_bilibili_hot_topics,
    fetch_hot_topics,
    parse_bilibili_popular,
    parse_bilibili_region,
    parse_bilibili_search,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def test_parse_bilibili_popular_sorts_by_traffic_and_normalizes_video_fields():
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "title": "低播放视频",
                    "bvid": "BVLOW",
                    "aid": 1,
                    "cid": 11,
                    "pic": "//i0.hdslb.com/low.jpg",
                    "desc": "低播放简介",
                    "duration": 120,
                    "tid": 76,
                    "tname": "美食制作",
                    "owner": {"name": "UP低", "mid": 10},
                    "stat": {"view": 100, "like": 5, "danmaku": 2, "favorite": 1, "coin": 1, "share": 0, "reply": 3},
                },
                {
                    "title": "高播放视频",
                    "bvid": "BVHIGH",
                    "aid": 2,
                    "cid": 22,
                    "pic": "https://i0.hdslb.com/high.jpg",
                    "desc": "高播放简介",
                    "duration": 90,
                    "tid": 160,
                    "tname": "生活",
                    "owner": {"name": "UP高", "mid": 20},
                    "stat": {"view": 9999, "like": 55, "danmaku": 12, "favorite": 10, "coin": 8, "share": 7, "reply": 6},
                },
            ]
        },
    }

    topics = parse_bilibili_popular(payload)

    assert [topic["title"] for topic in topics] == ["高播放视频", "低播放视频"]
    assert topics[0]["rank"] == 1
    assert topics[0]["url"] == "https://www.bilibili.com/video/BVHIGH"
    assert topics[0]["hot_value"] == 9999
    assert topics[0]["cover"] == "https://i0.hdslb.com/high.jpg"
    assert topics[1]["cover"] == "https://i0.hdslb.com/low.jpg"
    assert topics[0]["metrics"]["like"] == 55
    assert topics[0]["source"] == "B站"
    assert topics[0]["type"] == "video"


def test_parse_bilibili_search_strips_html_duration_and_chinese_counts():
    payload = {
        "code": 0,
        "data": {
            "result": [
                {
                    "title": "<em class=\"keyword\">草原</em>旅行",
                    "arcurl": "http://www.bilibili.com/video/BVSEARCH",
                    "bvid": "BVSEARCH",
                    "aid": 3,
                    "pic": "//i1.hdslb.com/search.jpg",
                    "description": "搜索简介",
                    "duration": "01:02:03",
                    "typeid": 211,
                    "typename": "美食",
                    "author": "UP搜索",
                    "mid": 30,
                    "play": "1.2万",
                    "video_review": "34",
                    "favorites": "56",
                    "review": "7",
                    "like": "890",
                }
            ]
        },
    }

    topics = parse_bilibili_search(payload)

    assert topics[0]["title"] == "草原旅行"
    assert topics[0]["url"] == "https://www.bilibili.com/video/BVSEARCH"
    assert topics[0]["cover"] == "https://i1.hdslb.com/search.jpg"
    assert topics[0]["duration"] == 3723
    assert topics[0]["hot_value"] == 12000
    assert topics[0]["metrics"]["danmaku"] == 34


def test_parse_bilibili_region_normalizes_legacy_ranking_shape():
    payload = {
        "code": 0,
        "data": [
            {
                "title": "分区视频",
                "bvid": "BVREGION",
                "aid": 4,
                "pic": "//i2.hdslb.com/region.jpg",
                "duration": "7:04",
                "typename": "生活",
                "author": "UP分区",
                "mid": 40,
                "play": 3456,
                "video_review": 78,
                "review": 9,
                "favorites": 10,
                "coins": 11,
                "pts": 123,
            }
        ],
    }

    topics = parse_bilibili_region(payload)

    assert topics[0]["title"] == "分区视频"
    assert topics[0]["duration"] == 424
    assert topics[0]["hot_value"] == 3456
    assert topics[0]["metrics"]["score"] == 123


def test_fetch_bilibili_hot_topics_uses_search_keyword_category_and_order_click():
    payload = {"code": 0, "data": {"result": [{"title": "A", "bvid": "BVA", "play": 1}]}}

    with patch("urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
        topics = fetch_bilibili_hot_topics(limit=1, keyword="草原", category="211")

    request = urlopen.call_args.args[0]
    assert "x/web-interface/search/type" in request.full_url
    assert "keyword=%E8%8D%89%E5%8E%9F" in request.full_url
    assert "order=click" in request.full_url
    assert "tids=211" in request.full_url
    assert topics[0]["title"] == "A"


def test_fetch_bilibili_hot_topics_maps_travel_to_valid_chuxing_region():
    payload = {"code": 0, "data": [{"title": "出行视频", "bvid": "BVTRAVEL", "play": 1, "typename": "出行"}]}

    with patch("urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
        topics = fetch_bilibili_hot_topics(limit=1, category="travel")

    request = urlopen.call_args.args[0]
    assert "x/web-interface/ranking/region" in request.full_url
    assert "rid=250" in request.full_url
    assert "rid=96" not in request.full_url
    assert topics[0]["title"] == "出行视频"


def test_fetch_bilibili_hot_topics_uses_region_for_category_without_keyword():
    payload = {"code": 0, "data": [{"title": "A", "bvid": "BVA", "play": 1}]}

    with patch("urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
        fetch_bilibili_hot_topics(limit=1, category="life")

    request = urlopen.call_args.args[0]
    assert "x/web-interface/ranking/region" in request.full_url
    assert "rid=160" in request.full_url


def test_fetch_hot_topics_dispatches_bilibili_aliases():
    with patch("hotstream.scraper.fetch_bilibili_hot_topics", return_value=[{"title": "B"}]) as fetch:
        assert fetch_hot_topics("bilibili", limit=1)[0]["title"] == "B"
        assert fetch_hot_topics("b站", limit=1)[0]["title"] == "B"
        assert fetch_hot_topics("哔哩哔哩", limit=1)[0]["title"] == "B"

    assert fetch.call_count == 3


def test_fetch_bilibili_hot_topics_handles_api_code_error():
    with patch("urllib.request.urlopen", return_value=FakeResponse({"code": -352, "message": "风控"})):
        with pytest.raises(RuntimeError, match="Bilibili API error"):
            fetch_bilibili_hot_topics(limit=1)
