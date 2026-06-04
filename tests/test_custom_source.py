"""Tests for build_custom_topic in hotstream.image_scraper.

All tests are offline: _read_url is monkeypatched to return synthetic HTML
fixtures so no network calls are made.
"""
from __future__ import annotations

import pytest

from hotstream.image_scraper import (
    build_custom_topic,
    _extract_aweme_id,
    _is_douyin_url,
    _parse_douyin_share_page,
)


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

VIDEO_HTML = """\
<html>
<head>
  <meta property="og:title" content="精彩视频：春日牧场" />
  <meta property="og:description" content="这是一段关于春日牧场的精彩视频简介。" />
  <meta property="og:image" content="https://cdn.example.com/cover.jpg" />
  <meta property="og:video" content="https://cdn.example.com/video.mp4" />
  <meta property="og:type" content="video.other" />
</head>
<body><p>视频内容</p></body>
</html>
"""

ARTICLE_HTML = """\
<html>
<head>
  <meta property="og:title" content="文章标题：秋日赏景指南" />
  <meta property="og:description" content="这是一篇关于秋日赏景的文章简介。" />
  <meta property="og:image" content="https://cdn.example.com/article-cover.jpg" />
  <meta property="og:type" content="article" />
</head>
<body><p>文章正文内容</p></body>
</html>
"""

TWITTER_VIDEO_HTML = """\
<html>
<head>
  <meta property="og:title" content="Twitter 播放器页面" />
  <meta name="twitter:player" content="https://player.example.com/embed/123" />
  <meta property="og:image" content="https://cdn.example.com/tw-cover.jpg" />
</head>
<body></body>
</html>
"""

BARE_VIDEO_TAG_HTML = """\
<html>
<head>
  <title>内嵌视频页面</title>
</head>
<body>
  <video src="https://cdn.example.com/clip.mp4" controls></video>
</body>
</html>
"""

PLAY_ADDR_HTML = """\
<html>
<head><title>抖音风格页面</title></head>
<body>
  <script>var playAddr = "https://v.example.com/abc.mp4";</script>
</body>
</html>
"""

MINIMAL_HTML = """\
<html>
<head><title>极简页面</title></head>
<body><p>只有正文，无任何视频信号。</p></body>
</html>
"""

RELATIVE_COVER_HTML = """\
<html>
<head>
  <meta property="og:title" content="相对路径封面测试" />
  <meta property="og:image" content="/images/cover.jpg" />
</head>
<body></body>
</html>
"""

NO_TITLE_HTML = """\
<html>
<head></head>
<body><p>没有标题的页面。</p></body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_read_url(html: str):
    """Return a monkeypatch replacement for _read_url that returns *html*."""

    def _read_url(_url: str, timeout: int = 10) -> str:  # noqa: ARG001
        return html

    return _read_url


def _failing_read_url(_url: str, timeout: int = 10) -> str:  # noqa: ARG001
    raise OSError("network error")


# ---------------------------------------------------------------------------
# Tests: has_video via og:video in HTML
# ---------------------------------------------------------------------------

def test_build_custom_topic_og_video_sets_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(VIDEO_HTML))
    topic = build_custom_topic("https://example.com/video-page")
    assert topic["has_video"] is True
    assert topic["type"] == "video"


# ---------------------------------------------------------------------------
# Tests: pure article HTML — no video signals
# ---------------------------------------------------------------------------

def test_build_custom_topic_article_html_has_video_false(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://example.com/article")
    assert topic["has_video"] is False
    assert topic["type"] == "article"


def test_build_custom_topic_article_cover_from_og_image(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://example.com/article")
    assert topic["cover"] == "https://cdn.example.com/article-cover.jpg"


# ---------------------------------------------------------------------------
# Tests: title extraction
# ---------------------------------------------------------------------------

def test_build_custom_topic_title_from_og_title(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(VIDEO_HTML))
    topic = build_custom_topic("https://example.com/video-page")
    assert topic["title"] == "精彩视频：春日牧场"


def test_build_custom_topic_title_from_og_description(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://example.com/article")
    assert topic["desc"] == "这是一篇关于秋日赏景的文章简介。"


def test_build_custom_topic_title_fallback_to_html_title(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://example.com/minimal")
    assert topic["title"] == "极简页面"


def test_build_custom_topic_title_fallback_to_url_when_no_title(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(NO_TITLE_HTML))
    url = "https://example.com/no-title-page"
    topic = build_custom_topic(url)
    assert topic["title"] == url


# ---------------------------------------------------------------------------
# Tests: fixed fields — source, label, rank, metrics, hot_value
# ---------------------------------------------------------------------------

def test_build_custom_topic_source_and_label(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://example.com/article")
    assert topic["source"] == "自定义"
    assert topic["label"] == "自定义链接"
    assert topic["rank"] == 1
    assert topic["hot_value"] == 0
    assert topic["metrics"] == {}


def test_build_custom_topic_url_preserved(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    url = "https://example.com/article"
    topic = build_custom_topic(url)
    assert topic["url"] == url


# ---------------------------------------------------------------------------
# Tests: known video domain URL tokens → has_video True (regardless of HTML)
# ---------------------------------------------------------------------------

def test_build_custom_topic_bilibili_url_has_video_true(monkeypatch):
    """URL containing bilibili.com/video → has_video True even with plain HTML."""
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://www.bilibili.com/video/BV1xx411c7mD")
    assert topic["has_video"] is True
    assert topic["type"] == "video"


def test_build_custom_topic_douyin_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://www.douyin.com/video/7123456789")
    assert topic["has_video"] is True


def test_build_custom_topic_youtube_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(ARTICLE_HTML))
    topic = build_custom_topic("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert topic["has_video"] is True


def test_build_custom_topic_b23tv_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://b23.tv/BV1xx")
    assert topic["has_video"] is True


def test_build_custom_topic_iqiyi_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://www.ixigua.com/12345678")
    assert topic["has_video"] is True


def test_build_custom_topic_vqq_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://v.qq.com/x/cover/abc123.html")
    assert topic["has_video"] is True


def test_build_custom_topic_kuaishou_url_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://www.kuaishou.com/short-video/abc")
    assert topic["has_video"] is True


# ---------------------------------------------------------------------------
# Tests: video signals in page content (non-URL-based detection)
# ---------------------------------------------------------------------------

def test_build_custom_topic_twitter_player_sets_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(TWITTER_VIDEO_HTML))
    topic = build_custom_topic("https://example.com/tw-page")
    assert topic["has_video"] is True


def test_build_custom_topic_bare_video_tag_sets_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(BARE_VIDEO_TAG_HTML))
    topic = build_custom_topic("https://example.com/embed")
    assert topic["has_video"] is True


def test_build_custom_topic_playaddr_token_sets_has_video_true(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(PLAY_ADDR_HTML))
    topic = build_custom_topic("https://example.com/dy-style")
    assert topic["has_video"] is True


# ---------------------------------------------------------------------------
# Tests: cover normalisation
# ---------------------------------------------------------------------------

def test_build_custom_topic_relative_cover_resolved_to_https(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(RELATIVE_COVER_HTML))
    topic = build_custom_topic("https://example.com/page")
    # urljoin should resolve the relative path
    assert topic["cover"] == "https://example.com/images/cover.jpg"


def test_build_custom_topic_no_cover_returns_empty_string(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url(MINIMAL_HTML))
    topic = build_custom_topic("https://example.com/minimal")
    assert topic["cover"] == ""


# ---------------------------------------------------------------------------
# Tests: failure path
# ---------------------------------------------------------------------------

def test_build_custom_topic_raises_runtime_error_on_fetch_failure(monkeypatch):
    monkeypatch.setattr("hotstream.image_scraper._read_url", _failing_read_url)
    with pytest.raises(RuntimeError, match="无法抓取该链接"):
        build_custom_topic("https://example.com/unreachable")


# ---------------------------------------------------------------------------
# Fixtures: Douyin SPA JS shell (desktop UA returns no OG metadata)
# ---------------------------------------------------------------------------

# Real-world Douyin desktop-UA response: ~72KB of JS with no og:* tags.
DOUYIN_SPA_SHELL_HTML = """\
<html>
<head><title>抖音</title></head>
<body>
  <div id="app"></div>
  <script>/* SPA bootstrap JS */</script>
</body>
</html>
"""

# Synthetic iesdouyin share-page response with embedded _ROUTER_DATA.
_AWEME_ID = "7300000000000000001"
_DOUYIN_SHARE_TITLE = "春日牧场骑马探险 #旅游 #前山牧场"
_DOUYIN_SHARE_COVER = "https://p3-sign.douyinpic.com/tos-cn-p-0015/cover_fake.jpeg"

IESDOUYIN_SHARE_PAGE_HTML = f"""\
<html>
<head><title>抖音视频</title></head>
<body>
<script>
window._ROUTER_DATA = {{
  "loaderData": {{
    "video_(id)/page": {{
      "videoInfoRes": {{
        "item_list": [
          {{
            "aweme_id": "{_AWEME_ID}",
            "desc": "{_DOUYIN_SHARE_TITLE}",
            "video": {{
              "cover": {{
                "uri": "cover_fake",
                "url_list": ["{_DOUYIN_SHARE_COVER}"]
              }}
            }}
          }}
        ]
      }}
    }}
  }}
}}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers: Douyin mock callables
# ---------------------------------------------------------------------------

def _make_read_url_douyin(share_html: str = IESDOUYIN_SHARE_PAGE_HTML):
    """Return a _read_url stub that:
    - returns DOUYIN_SPA_SHELL_HTML for www.douyin.com (desktop UA fetch)
    - returns *share_html* for iesdouyin.com (share page fetch by _resolve_douyin)
    - returns DOUYIN_SPA_SHELL_HTML for any other URL
    """
    def _read_url(url: str, timeout: int = 10) -> str:  # noqa: ARG001
        if "iesdouyin.com" in url:
            return share_html
        return DOUYIN_SPA_SHELL_HTML
    return _read_url


def _make_resolve_douyin(title: str, cover: str):
    """Return a _resolve_douyin stub that always yields (title, cover)."""
    def _resolve_douyin(_url: str, _timeout: int = 10) -> tuple[str, str]:  # noqa: ARG001
        return title, cover
    return _resolve_douyin


# ---------------------------------------------------------------------------
# Tests: _extract_aweme_id
# ---------------------------------------------------------------------------

class TestExtractAwemeId:
    """Unit-test the aweme_id extractor for all supported URL shapes."""

    def test_video_path(self):
        url = "https://www.douyin.com/video/7300000000000000000"
        assert _extract_aweme_id(url) == "7300000000000000000"

    def test_note_path(self):
        url = "https://www.douyin.com/note/7300000000000000002"
        assert _extract_aweme_id(url) == "7300000000000000002"

    def test_share_video_path(self):
        url = "https://www.iesdouyin.com/share/video/7300000000000000003/"
        assert _extract_aweme_id(url) == "7300000000000000003"

    def test_modal_id_query_param(self):
        url = "https://www.douyin.com/discover?modal_id=7300000000000000004"
        assert _extract_aweme_id(url) == "7300000000000000004"

    def test_aweme_id_query_param(self):
        url = "https://www.douyin.com/?aweme_id=7300000000000000005"
        assert _extract_aweme_id(url) == "7300000000000000005"

    def test_item_id_query_param(self):
        url = "https://www.douyin.com/watch?item_id=7300000000000000006"
        assert _extract_aweme_id(url) == "7300000000000000006"

    def test_vid_query_param(self):
        url = "https://www.douyin.com/?vid=7300000000000000007"
        assert _extract_aweme_id(url) == "7300000000000000007"

    def test_short_link_no_id_returns_empty(self):
        url = "https://v.douyin.com/iXXXXXXXX/"
        assert _extract_aweme_id(url) == ""

    def test_non_douyin_url_returns_empty(self):
        assert _extract_aweme_id("https://example.com/page") == ""


# ---------------------------------------------------------------------------
# Tests: _is_douyin_url
# ---------------------------------------------------------------------------

class TestIsDouyinUrl:
    def test_www_douyin(self):
        assert _is_douyin_url("https://www.douyin.com/video/123") is True

    def test_iesdouyin(self):
        assert _is_douyin_url("https://www.iesdouyin.com/share/video/123/") is True

    def test_shortlink_host_is_douyin(self):
        # v.douyin.com ends with .douyin.com, so _is_douyin_url returns True.
        assert _is_douyin_url("https://v.douyin.com/iABCDEF/") is True

    def test_bilibili_not_douyin(self):
        assert _is_douyin_url("https://www.bilibili.com/video/BV1xx") is False


# ---------------------------------------------------------------------------
# Tests: _parse_douyin_share_page
# ---------------------------------------------------------------------------

class TestParseDouyinSharePage:
    def test_parses_title_and_cover(self):
        title, cover = _parse_douyin_share_page(IESDOUYIN_SHARE_PAGE_HTML)
        assert title == _DOUYIN_SHARE_TITLE
        assert cover == _DOUYIN_SHARE_COVER

    def test_empty_html_returns_empty_tuple(self):
        assert _parse_douyin_share_page("") == ("", "")

    def test_no_router_data_returns_empty_tuple(self):
        html = "<html><body><script>var x=1;</script></body></html>"
        assert _parse_douyin_share_page(html) == ("", "")

    def test_empty_item_list_returns_empty_tuple(self):
        html = """\
<html><body><script>
window._ROUTER_DATA = {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": []}}}}
</script></body></html>
"""
        assert _parse_douyin_share_page(html) == ("", "")

    def test_fallback_loader_key(self):
        """Any loaderData value dict with 'videoInfoRes' is accepted."""
        html = f"""\
<html><body><script>
window._ROUTER_DATA = {{
  "loaderData": {{
    "some_other_key/page": {{
      "videoInfoRes": {{
        "item_list": [
          {{
            "desc": "fallback title",
            "video": {{"cover": {{"url_list": ["{_DOUYIN_SHARE_COVER}"]}}}}
          }}
        ]
      }}
    }}
  }}
}}
</script></body></html>
"""
        title, cover = _parse_douyin_share_page(html)
        assert title == "fallback title"
        assert cover == _DOUYIN_SHARE_COVER


# ---------------------------------------------------------------------------
# Tests: build_custom_topic — Douyin URL (via _resolve_douyin mock)
# ---------------------------------------------------------------------------

class TestBuildCustomTopicDouyin:
    """Offline tests for the Douyin branch in build_custom_topic.

    Strategy: monkeypatch both _read_url (returns SPA JS shell) and
    _resolve_douyin (returns fixed title + cover) so the full function
    exercises the Douyin branch without any network calls.
    """

    def test_douyin_video_url_has_video_true(self, monkeypatch):
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin(_DOUYIN_SHARE_TITLE, _DOUYIN_SHARE_COVER),
        )
        topic = build_custom_topic(f"https://www.douyin.com/video/{_AWEME_ID}")
        assert topic["has_video"] is True
        assert topic["type"] == "video"

    def test_douyin_video_url_title_nonempty(self, monkeypatch):
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin(_DOUYIN_SHARE_TITLE, _DOUYIN_SHARE_COVER),
        )
        topic = build_custom_topic(f"https://www.douyin.com/video/{_AWEME_ID}")
        assert topic["title"]
        assert topic["title"] != f"https://www.douyin.com/video/{_AWEME_ID}"

    def test_douyin_video_url_cover_nonempty(self, monkeypatch):
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin(_DOUYIN_SHARE_TITLE, _DOUYIN_SHARE_COVER),
        )
        topic = build_custom_topic(f"https://www.douyin.com/video/{_AWEME_ID}")
        assert topic["cover"] == _DOUYIN_SHARE_COVER

    def test_douyin_short_link_has_video_true(self, monkeypatch):
        """v.douyin.com short links are video-domain-matched → has_video True."""
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin(_DOUYIN_SHARE_TITLE, _DOUYIN_SHARE_COVER),
        )
        topic = build_custom_topic("https://v.douyin.com/iXXXXXXXX/")
        assert topic["has_video"] is True

    def test_douyin_resolve_failure_no_raise(self, monkeypatch):
        """When _resolve_douyin returns ("", ""), build_custom_topic must not raise.

        has_video must still be True (URL-token match) even though title/cover
        degraded (cover empty, title falls back to URL).
        """
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin("", ""),
        )
        url = f"https://www.douyin.com/video/{_AWEME_ID}"
        topic = build_custom_topic(url)
        assert topic["has_video"] is True
        assert topic["cover"] == ""
        # title is non-empty (may be "<title>" from shell page or the URL itself)
        assert topic["title"]

    def test_douyin_cover_failure_does_not_block_has_video(self, monkeypatch):
        """Cover extraction failure must not flip has_video to False."""
        monkeypatch.setattr("hotstream.image_scraper._read_url", _make_read_url_douyin())
        monkeypatch.setattr(
            "hotstream.image_scraper._resolve_douyin",
            _make_resolve_douyin(_DOUYIN_SHARE_TITLE, ""),
        )
        topic = build_custom_topic(f"https://www.douyin.com/video/{_AWEME_ID}")
        assert topic["has_video"] is True
        assert topic["cover"] == ""
