"""Tests for build_custom_topic in hotstream.image_scraper.

All tests are offline: _read_url is monkeypatched to return synthetic HTML
fixtures so no network calls are made.
"""
from __future__ import annotations

import pytest

from hotstream.image_scraper import build_custom_topic


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
