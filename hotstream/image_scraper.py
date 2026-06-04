from __future__ import annotations

import gzip
import json
import re
import zlib
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

SOGOU_WEB_SEARCH_URL = "https://www.sogou.com/web"
DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"
BING_WEB_SEARCH_URL = "https://www.bing.com/search"
BING_IMAGE_SEARCH_URL = "https://www.bing.com/images/search"
CREATIVE_COMMONS_FILTER = "+filterui:license-L2_L3_L4_L5_L6_L7"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _build_request(url: str) -> Request:
    return Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        method="GET",
    )


def build_news_search_url(query: str) -> str:
    """Build a web search URL biased toward news articles about the topic."""
    normalized_query = (query or "热点新闻").strip() or "热点新闻"
    return f"{SOGOU_WEB_SEARCH_URL}?query={quote_plus(normalized_query + ' 新闻')}"


def build_image_search_url(query: str) -> str:
    """Build a Bing image search URL for related, broadly reusable images."""
    normalized_query = (query or "热点新闻").strip() or "热点新闻"
    return (
        f"{BING_IMAGE_SEARCH_URL}?"
        f"q={quote_plus(normalized_query)}"
        f"&form=HDRSC2"
        f"&qft={CREATIVE_COMMONS_FILTER}"
    )


def _decode_search_result_url(raw_url: str) -> str:
    url = unescape(raw_url).strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(uddg).strip()
    return url


def extract_news_result_urls(html: str, limit: int = 30) -> list[str]:
    """Extract article URLs from a search results page."""
    safe_limit = max(1, min(30, int(limit or 30)))
    urls: list[str] = []
    seen: set[str] = set()
    result_blocks = re.findall(r'<div\b[^>]*class=["\'][^"\']*vrwrap[^"\']*["\'][^>]*>(.*?)</div>', html, flags=re.IGNORECASE | re.DOTALL)
    if not result_blocks:
        result_blocks = re.findall(r'<a\b[^>]*class=["\'][^"\']*result__a[^"\']*["\'][^>]*>', html, flags=re.IGNORECASE | re.DOTALL)
    if not result_blocks:
        result_blocks = re.findall(r'<li\b[^>]*class=["\'][^"\']*b_algo[^"\']*["\'][^>]*>(.*?)</li>', html, flags=re.IGNORECASE | re.DOTALL)
    if not result_blocks:
        result_blocks = re.findall(r'<div\b[^>]*class=["\'][^"\']*(?:news-card|card-with-cluster)[^"\']*["\'][^>]*>(.*?)</div>', html, flags=re.IGNORECASE | re.DOTALL)
    for block in result_blocks:
        match = re.search(r'href=["\']([^"\']+)["\']', block, flags=re.IGNORECASE)
        if not match:
            continue
        url = _decode_search_result_url(match.group(1))
        if not url.startswith(("http://", "https://")):
            continue
        if "bing.com" in url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= safe_limit:
            break
    return urls


def _meta_content(html: str, key: str) -> str:
    patterns = [
        rf'<meta\s+[^>]*(?:property|name)=["\']{re.escape(key)}["\'][^>]*content=["\']([^"\']+)["\']',
        rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return unescape(match.group(1)).strip()
    return ""


def _looks_like_content_image(url: str) -> bool:
    lowered = url.lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    has_image_extension = bool(re.search(r'\.(?:jpg|jpeg|png|webp)(?:[?#].*)?$', lowered))
    image_host_or_path = any(token in lowered for token in ("image", "img", "photo", "pic", "inews.gtimg.com", "qpic.cn"))
    if not has_image_extension and not image_host_or_path:
        return False
    blocked_tokens = (
        "logo", "icon", "avatar", "sprite", "qr", "qrcode", "barcode",
        "blank", "placeholder", "default", "1x1", "spacer", "loading",
        "praise", "comment", "favor", "share", "browser", "qqbrowser", "dark", "200200",
    )
    return not any(token in lowered for token in blocked_tokens)


def extract_article_image_candidates(
    html: str,
    article_url: str,
    source_title: str = "新闻报道",
) -> list[dict[str, str]]:
    """Extract likely article images from a news article HTML page."""
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_image(raw_url: str, title: str) -> None:
        normalized_title = title.strip() or source_title or "新闻图片"
        if any(token in normalized_title for token in ("头像", "作者", "二维码", "图标")):
            return
        image_url = urljoin(article_url, unescape(raw_url).strip())
        if not _looks_like_content_image(image_url) or image_url in seen:
            return
        seen.add(image_url)
        results.append({
            "url": image_url,
            "thumbnail": image_url,
            "title": normalized_title,
            "source_url": article_url,
            "source": "新闻原文",
        })

    og_image = _meta_content(html, "og:image") or _meta_content(html, "twitter:image")
    if og_image:
        add_image(og_image, f"{source_title} 封面图".strip())

    article_match = re.search(r'<article\b[^>]*>(.*?)</article>', html, flags=re.IGNORECASE | re.DOTALL)
    search_area = article_match.group(1) if article_match else html
    for img_tag in re.findall(r'<img\b[^>]*>', search_area, flags=re.IGNORECASE | re.DOTALL):
        src_match = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+)["\']', img_tag, flags=re.IGNORECASE)
        if not src_match:
            continue
        alt_match = re.search(r'alt=["\']([^"\']*)["\']', img_tag, flags=re.IGNORECASE)
        title = unescape(alt_match.group(1)).strip() if alt_match else source_title
        add_image(src_match.group(1), title)
    return results


def _extract_bing_metadata(html: str) -> list[dict[str, Any]]:
    matches = re.findall(r"\bm=(['\"])(.*?)\1", html, flags=re.DOTALL)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, raw_metadata in matches:
        try:
            metadata = json.loads(unescape(raw_metadata))
        except (json.JSONDecodeError, TypeError):
            continue

        image_url = str(metadata.get("murl") or "").strip()
        if not image_url.startswith(("http://", "https://")) or image_url in seen:
            continue
        seen.add(image_url)
        results.append({
            "url": image_url,
            "thumbnail": str(metadata.get("turl") or image_url).strip(),
            "title": str(metadata.get("t") or "相关图片").strip() or "相关图片",
        })
    return results


def _read_url(url: str, timeout: int) -> str:
    with urlopen(_build_request(url), timeout=timeout) as response:
        raw = response.read()
        encoding = response.headers.get("Content-Encoding")
    # Only act on a real string header; mocked/absent headers fall through
    # untouched so plain (uncompressed) responses are returned as-is.
    encoding = encoding.lower() if isinstance(encoding, str) else ""
    if not isinstance(raw, (bytes, bytearray)):
        return str(raw)
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError):
            pass
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error:
                pass
    return raw.decode("utf-8", errors="replace")


def _fetch_images_from_news_articles(query: str, limit: int, timeout: int) -> list[dict[str, str]]:
    search_html = _read_url(build_news_search_url(query), timeout=timeout)
    article_urls = extract_news_result_urls(search_html, limit=limit)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for article_url in article_urls:
        if len(results) >= limit:
            break
        if any(token in article_url.lower() for token in ("share-video", "douyin.com/video", "v.qq.com")):
            continue
        try:
            article_html = _read_url(article_url, timeout=timeout)
        except Exception:
            continue
        for image in extract_article_image_candidates(article_html, article_url, source_title=query):
            image_url = image["url"]
            if image_url in seen:
                continue
            seen.add(image_url)
            results.append(image)
            if len(results) >= limit:
                break
    return results


def _fetch_images_from_image_search(query: str, limit: int, timeout: int) -> list[dict[str, str]]:
    html = _read_url(build_image_search_url(query), timeout=timeout)
    return _extract_bing_metadata(html)[:limit]


# Known video domains / path tokens. Presence of any of these in a URL is a
# strong signal that the link points at (or embeds) a video.
_VIDEO_URL_TOKENS = (
    "bilibili.com/video",
    "b23.tv",
    "douyin.com",
    "v.douyin.com",
    "iesdouyin",
    "youtube.com",
    "youtu.be",
    "v.qq.com",
    "ixigua.com",
    "kuaishou.com",
    "kuaishou.cn",
    "weibo.com/tv",
    "weibo.com/show",
    "haokan.baidu",
    "miaopai",
    "/video/",
    "/watch",
)

# Page-level markers that indicate the HTML carries a playable video.
_VIDEO_HTML_TOKENS = (
    "playaddr",
    "play_url",
    "videourl",
)


def _normalize_https(url: str) -> str:
    """Normalize a (possibly protocol-relative) URL to an https URL."""
    value = unescape(str(url or "")).strip()
    if not value:
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("http://"):
        return "https://" + value[len("http://"):]
    return value


def _detect_video(url: str, html: str) -> bool:
    """Detect whether a link/page points at or embeds a video.

    Two independent checks; either one is sufficient:
      (a) the URL contains a known video domain/path token;
      (b) the page exposes video metadata/markup (og:video*, og:type=video,
          twitter:player, a <video> tag, or inline play-address fields).
    """
    lowered_url = (url or "").lower()
    if any(token in lowered_url for token in _VIDEO_URL_TOKENS):
        return True

    if _meta_content(html, "og:video") or _meta_content(html, "og:video:url") or _meta_content(html, "og:video:secure_url"):
        return True
    if "video" in (_meta_content(html, "og:type") or "").lower():
        return True
    if _meta_content(html, "twitter:player"):
        return True

    lowered_html = (html or "").lower()
    if "<video" in lowered_html:
        return True
    if any(token in lowered_html for token in _VIDEO_HTML_TOKENS):
        return True
    return False


def build_custom_topic(url: str, timeout: int = 10) -> dict[str, Any]:
    """Fetch an arbitrary URL and build a single topic dict from its metadata.

    Extracts title/description/cover from Open Graph / Twitter / standard tags
    and decides whether the link carries a video. The returned shape mirrors the
    topics produced by the hot-list sources so the rest of the pipeline (Qwen
    analysis + DeepSeek copy generation) treats it uniformly.

    Raises ``RuntimeError`` if the page cannot be fetched.
    """
    target = str(url or "").strip()
    try:
        html = _read_url(target, timeout=timeout)
    except Exception as exc:
        raise RuntimeError(f"无法抓取该链接：{exc}") from exc

    title = (
        _meta_content(html, "og:title")
        or _meta_content(html, "twitter:title")
    )
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            title = unescape(title_match.group(1)).strip()
    if not title:
        title = target

    desc = (
        _meta_content(html, "og:description")
        or _meta_content(html, "description")
        or ""
    )

    cover_raw = _meta_content(html, "og:image") or _meta_content(html, "twitter:image") or ""
    cover = _normalize_https(urljoin(target, cover_raw)) if cover_raw else ""

    has_video = _detect_video(target, html)

    return {
        "rank": 1,
        "title": title,
        "url": target,
        "cover": cover,
        "desc": desc,
        "label": "自定义链接",
        "source": "自定义",
        "type": "video" if has_video else "article",
        "has_video": has_video,
        "hot_value": 0,
        "metrics": {},
    }


def fetch_related_images(query: str, limit: int = 30, timeout: int = 8) -> list[dict[str, str]]:
    """Fetch images from news articles about the same topic.

    This prefers pictures chosen by publishers for the same news topic instead of
    generic image-search matches. Failures return an empty list so copy generation
    is not blocked by image lookup.
    """
    safe_limit = max(1, min(30, int(limit or 30)))
    try:
        return _fetch_images_from_news_articles(query, safe_limit, timeout)[:safe_limit]
    except Exception:
        return []
