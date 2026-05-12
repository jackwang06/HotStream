import json
from unittest.mock import patch

from hotstream.scraper import (
    fetch_hot_topics,
    fetch_xiaohongshu_hot_topics,
    fetch_zhihu_hot_topics,
    parse_xiaohongshu_explore_page,
    parse_zhihu_hot_list,
)


def test_parse_zhihu_hot_list_normalizes_topics():
    payload = {
        "data": [
            {
                "target": {
                    "title": "知乎热点一",
                    "url": "https://api.zhihu.com/questions/123",
                    "excerpt": "热点摘要",
                },
                "detail_text": "1000 万热度",
            },
            {
                "target": {
                    "title": "知乎热点二",
                    "url": "https://api.zhihu.com/questions/456",
                },
                "detail_text": "50 万热度",
            },
        ]
    }

    topics = parse_zhihu_hot_list(payload)

    assert topics[0] == {
        "rank": 1,
        "title": "知乎热点一",
        "url": "https://www.zhihu.com/question/123",
        "hot_value": 10000000,
        "label": "热点摘要",
        "source": "知乎",
    }
    assert topics[1]["hot_value"] == 500000
    assert topics[1]["source"] == "知乎"


def test_parse_xiaohongshu_explore_page_normalizes_initial_feed_notes():
    state = {
        "feed": {
            "feeds": [
                {
                    "noteCard": {
                        "displayTitle": "小红书热点笔记一",
                        "noteId": "note-1",
                        "interactInfo": {"likedCount": "1.2万"},
                    }
                },
                {
                    "noteCard": {
                        "displayTitle": "小红书热点笔记二",
                        "noteId": "note-2",
                        "interactInfo": {"likedCount": "888"},
                    }
                },
            ]
        }
    }
    html = f'<script>window.__INITIAL_STATE__={json.dumps(state, ensure_ascii=False)}</script>'

    topics = parse_xiaohongshu_explore_page(html)

    assert topics == [
        {
            "rank": 1,
            "title": "小红书热点笔记一",
            "url": "https://www.xiaohongshu.com/explore/note-1",
            "hot_value": 12000,
            "label": "1.2万赞",
            "source": "小红书",
        },
        {
            "rank": 2,
            "title": "小红书热点笔记二",
            "url": "https://www.xiaohongshu.com/explore/note-2",
            "hot_value": 888,
            "label": "888赞",
            "source": "小红书",
        },
    ]


def test_fetch_zhihu_hot_topics_uses_mobile_public_endpoint_and_limit():
    body = json.dumps({
        "data": [
            {"target": {"title": "A", "url": "https://api.zhihu.com/questions/1"}, "detail_text": "1 万热度"},
            {"target": {"title": "B", "url": "https://api.zhihu.com/questions/2"}, "detail_text": "2 万热度"},
        ]
    }).encode("utf-8")

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return body

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        topics = fetch_zhihu_hot_topics(limit=1)

    assert [topic["title"] for topic in topics] == ["A"]
    request = urlopen.call_args.args[0]
    assert "api.zhihu.com/topstory/hot-list" in request.full_url


def test_fetch_xiaohongshu_hot_topics_uses_explore_page_and_limit():
    html = '<script>window.__INITIAL_STATE__={"feed":{"feeds":[{"noteCard":{"displayTitle":"A","noteId":"1","interactInfo":{"likedCount":"9"}}},{"noteCard":{"displayTitle":"B","noteId":"2","interactInfo":{"likedCount":"8"}}}]}}</script>'

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return html.encode("utf-8")

    with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
        topics = fetch_xiaohongshu_hot_topics(limit=1)

    assert [topic["title"] for topic in topics] == ["A"]
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://www.xiaohongshu.com/explore"


def test_fetch_hot_topics_dispatches_supported_sources():
    with patch("hotstream.scraper.fetch_toutiao_hot_topics", return_value=[{"title": "T"}]), \
         patch("hotstream.scraper.fetch_zhihu_hot_topics", return_value=[{"title": "Z"}]), \
         patch("hotstream.scraper.fetch_xiaohongshu_hot_topics", return_value=[{"title": "X"}]):
        assert fetch_hot_topics("toutiao", limit=1)[0]["title"] == "T"
        assert fetch_hot_topics("zhihu", limit=1)[0]["title"] == "Z"
        assert fetch_hot_topics("xiaohongshu", limit=1)[0]["title"] == "X"
