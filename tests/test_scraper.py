import json
from types import SimpleNamespace
from unittest.mock import patch

from hotstream.scraper import parse_toutiao_hot_board, fetch_toutiao_hot_topics


def test_parse_toutiao_hot_board_normalizes_topics():
    payload = {
        "data": [
            {
                "ClusterId": 123,
                "Title": "测试热点一",
                "Url": "https://www.toutiao.com/trending/123/",
                "HotValue": "987654",
                "Label": "hot",
            },
            {
                "ClusterId": 456,
                "Title": "测试热点二",
                "Url": "https://www.toutiao.com/trending/456/",
                "HotValue": 12345,
                "Label": "",
            },
        ]
    }

    topics = parse_toutiao_hot_board(payload)

    assert topics == [
        {
            "rank": 1,
            "title": "测试热点一",
            "url": "https://www.toutiao.com/trending/123/",
            "hot_value": 987654,
            "label": "hot",
            "source": "今日头条",
        },
        {
            "rank": 2,
            "title": "测试热点二",
            "url": "https://www.toutiao.com/trending/456/",
            "hot_value": 12345,
            "label": "",
            "source": "今日头条",
        },
    ]


def test_fetch_toutiao_hot_topics_uses_live_endpoint_and_limit():
    body = json.dumps({
        "data": [
            {"ClusterId": 1, "Title": "A", "Url": "https://example.com/a", "HotValue": 10},
            {"ClusterId": 2, "Title": "B", "Url": "https://example.com/b", "HotValue": 9},
        ]
    }).encode("utf-8")

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        topics = fetch_toutiao_hot_topics(limit=1)

    assert len(topics) == 1
    assert topics[0]["title"] == "A"
    request = urlopen.call_args.args[0]
    assert "toutiao.com/hot-event/hot-board/" in request.full_url
    assert request.headers["User-agent"].startswith("Mozilla/5.0")
