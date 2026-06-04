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
# Some SPA sites (notably Douyin) only server-side render Open Graph / structured
# metadata for mobile/crawler clients. Falling back to this UA lets us recover a
# title + cover that the desktop UA fetch leaves empty.
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1"
)


def _build_request(url: str, user_agent: str = USER_AGENT) -> Request:
    return Request(
        url,
        headers={
            "User-Agent": user_agent,
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


def _read_url(url: str, timeout: int, user_agent: str = USER_AGENT) -> str:
    with urlopen(_build_request(url, user_agent), timeout=timeout) as response:
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


def _read_url_with_ua(url: str, timeout: int, user_agent: str) -> str:
    """Fetch *url* using *user_agent*, degrading gracefully when ``_read_url`` is
    mocked with the legacy ``(url, timeout)`` signature.

    The custom-source tests monkeypatch ``_read_url`` with a 2-arg stub that does
    not accept ``user_agent``; calling it with the keyword would raise
    ``TypeError``. We catch that and retry without the UA so both the real (UA-
    aware) implementation and the test doubles work unchanged.
    """
    try:
        return _read_url(url, timeout, user_agent=user_agent)
    except TypeError:
        return _read_url(url, timeout)


# Douyin / Iesdouyin domains we know how to resolve into a share page.
_DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")
# Short-link hosts that 3xx-redirect to a URL carrying the aweme_id.
_DOUYIN_SHORTLINK_HOSTS = ("v.douyin.com", "z.douyin.com")


def _is_douyin_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in _DOUYIN_HOSTS)


def _extract_aweme_id(url: str) -> str:
    """Pull the 19-ish digit aweme/video id out of a Douyin URL, if present."""
    match = re.search(r"/(?:video|note|share/video|share/note)/(\d{6,25})", url)
    if match:
        return match.group(1)
    query = parse_qs(urlparse(url).query)
    for key in ("modal_id", "aweme_id", "item_id", "vid"):
        values = query.get(key) or []
        if values and values[0].isdigit():
            return values[0]
    return ""


def _resolve_shortlink(url: str, timeout: int) -> str:
    """Follow a Douyin short link to its final URL (which carries the aweme_id).

    urllib follows redirects by default, so a normal mobile-UA fetch lands on the
    expanded URL; ``response.geturl()`` returns it. Returns the original URL on
    any failure so callers can fall back.
    """
    try:
        request = _build_request(url, MOBILE_USER_AGENT)
        with urlopen(request, timeout=timeout) as response:
            return response.geturl() or url
    except Exception:
        return url


def _parse_douyin_share_page(html: str) -> tuple[str, str]:
    """Extract (title, cover) from an iesdouyin /share/video SSR page.

    The page embeds ``window._ROUTER_DATA`` whose
    ``loaderData["video_(id)/page"].videoInfoRes.item_list[0]`` holds ``desc``
    (the caption / title) and ``video.cover`` (plus origin/dynamic fallbacks).
    Returns ("", "") if the structure is missing or the item was filtered out.
    """
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", html, flags=re.DOTALL)
    if not match:
        return "", ""
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return "", ""

    loader = data.get("loaderData") if isinstance(data, dict) else None
    if not isinstance(loader, dict):
        return "", ""
    # The key literally contains "(id)"; fall back to any *page entry holding it.
    page = loader.get("video_(id)/page")
    if not isinstance(page, dict):
        for value in loader.values():
            if isinstance(value, dict) and "videoInfoRes" in value:
                page = value
                break
    if not isinstance(page, dict):
        return "", ""

    info = page.get("videoInfoRes")
    items = info.get("item_list") if isinstance(info, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return "", ""
    item = items[0]

    title = str(item.get("desc") or "").strip()
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    cover = ""
    for cover_key in ("cover", "origin_cover", "dynamic_cover"):
        candidate = video.get(cover_key) if isinstance(video, dict) else None
        url_list = candidate.get("url_list") if isinstance(candidate, dict) else None
        if isinstance(url_list, list):
            for raw in url_list:
                normalized = _normalize_https(raw)
                if normalized:
                    cover = normalized
                    break
        if cover:
            break
    return title, cover


def _resolve_douyin(url: str, timeout: int) -> tuple[str, str]:
    """Best-effort (title, cover) for a Douyin video link.

    Resolves short links, extracts the aweme_id, then reads the iesdouyin share
    page with a mobile UA and parses its embedded structured data. Never raises;
    returns ("", "") so ``build_custom_topic`` can fall back to generic OG tags.
    """
    try:
        target = url
        host = urlparse(url).netloc.lower()
        if any(host == h or host.endswith("." + h) for h in _DOUYIN_SHORTLINK_HOSTS):
            target = _resolve_shortlink(url, timeout)

        aweme_id = _extract_aweme_id(target) or _extract_aweme_id(url)
        if not aweme_id:
            return "", ""

        share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
        html = _read_url_with_ua(share_url, timeout, MOBILE_USER_AGENT)
        return _parse_douyin_share_page(html)
    except Exception:
        return "", ""


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

    # Douyin is a heavily anti-scraped SPA: a desktop-UA fetch returns a JS shell
    # with empty OG tags, so title/cover come back blank (title falls back to the
    # URL). Resolve the real caption + cover via the iesdouyin share page. Any
    # failure leaves the generic-OG values untouched.
    if _is_douyin_url(target):
        dy_title, dy_cover = _resolve_douyin(target, min(timeout, 8))
        if dy_title and (not title or title == target):
            title = dy_title
        if dy_cover:
            cover = dy_cover

    # Generic SPA fallback: if a desktop-UA fetch yielded no cover image, retry
    # once with a mobile/crawler UA, which many SPAs server-side render OG for.
    # Skipped for Douyin — _resolve_douyin already did the mobile-UA share-page
    # work, so this would only add a redundant (and latency-bounding) fetch.
    if not cover and not _is_douyin_url(target):
        try:
            mobile_html = _read_url_with_ua(target, min(timeout, 8), MOBILE_USER_AGENT)
        except Exception:
            mobile_html = ""
        if mobile_html:
            if not title or title == target:
                mobile_title = (
                    _meta_content(mobile_html, "og:title")
                    or _meta_content(mobile_html, "twitter:title")
                )
                if mobile_title:
                    title = mobile_title
            if not desc:
                desc = (
                    _meta_content(mobile_html, "og:description")
                    or _meta_content(mobile_html, "description")
                    or desc
                )
            mobile_cover = (
                _meta_content(mobile_html, "og:image")
                or _meta_content(mobile_html, "twitter:image")
                or ""
            )
            if mobile_cover:
                cover = _normalize_https(urljoin(target, mobile_cover))
            if not has_video:
                has_video = _detect_video(target, mobile_html)

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
