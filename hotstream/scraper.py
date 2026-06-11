from __future__ import annotations

import html
import json
import re
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode

TOUTIAO_HOT_BOARD_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
ZHIHU_HOT_LIST_URL = "https://api.zhihu.com/topstory/hot-list?limit={limit}&reverse_order=0"
XIAOHONGSHU_EXPLORE_URL = "https://www.xiaohongshu.com/explore"

# Largest internal page size used to over-fetch a source before category
# filtering, so topic-keyword filters always have ample material to match.
FETCH_ALL_LIMIT = 100

# Unified topic taxonomy shared across every source. ``keywords`` drives the
# substring topic filter; ``bili_rid`` (when present) is the native Bilibili
# region id used for region/search ranking. Sources without a native category
# concept rely purely on ``keywords`` filtering.
CATEGORIES: dict[str, dict[str, Any]] = {
    "all": {"label": "全部", "keywords": []},
    "travel": {
        "label": "出行·旅行",
        "bili_rid": "250",
        "keywords": ["旅行", "旅游", "出行", "出游", "景区", "景点", "自驾", "露营",
                     "度假", "攻略", "打卡", "民宿", "酒店", "风光", "户外", "徒步", "周边游"],
    },
    "food": {
        "label": "美食",
        "bili_rid": "211",
        "keywords": ["美食", "小吃", "火锅", "烧烤", "探店", "美味",
                     "零食", "特产", "餐厅", "厨艺"],
    },
    "rural": {
        "label": "乡村·三农",
        "keywords": ["乡村", "农村", "农业", "丰收", "田园", "牧场", "草原", "牧民",
                     "放牧", "采摘", "农家", "三农", "牛羊"],
    },
    "culture": {
        "label": "文化·民俗",
        "keywords": ["文化", "非遗", "民俗", "古镇", "博物", "展", "演出", "节",
                     "传统", "民族", "手工", "戏"],
    },
    "life": {
        "label": "生活",
        "bili_rid": "160",
        "keywords": ["生活", "日常", "vlog", "好物", "家居", "宠物", "亲子"],
    },
    "entertainment": {
        "label": "娱乐",
        "bili_rid": "5",
        "keywords": ["明星", "综艺", "演唱会", "影视", "剧", "娱乐", "电影", "音乐"],
    },
    "knowledge": {
        "label": "知识",
        "bili_rid": "36",
        "keywords": ["知识", "科普", "历史", "教育", "文化"],
    },
    "technology": {
        "label": "科技",
        "bili_rid": "188",
        "keywords": ["科技", "数码", "AI", "人工智能", "手机", "互联网", "智能"],
    },
}

def classify_topic_tag(topic: dict[str, Any]) -> str:
    """据标题/标签/简介匹配 CATEGORIES 关键词，返回首个命中的类别标签作为 tag（无则空串）。

    与 _filter_topics_by_category 同一套关键词，保证"分类筛选"与"tag 标注"口径一致。
    """
    text = " ".join(str(topic.get(k) or "") for k in ("title", "label", "desc")).lower()
    if not text.strip():
        return ""
    for key, cfg in CATEGORIES.items():
        if key == "all":
            continue
        for kw in cfg.get("keywords", []):
            if kw and kw.lower() in text:
                return str(cfg.get("label") or "")
    return ""


def tag_topics(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给每个 topic 补一个 'tag' 字段（已有非空则不覆盖）。原地修改并返回。"""
    for t in topics:
        if isinstance(t, dict) and not t.get("tag"):
            t["tag"] = classify_topic_tag(t)
    return topics


SOURCE_LABELS = {
    "toutiao": "今日头条",
    "zhihu": "知乎",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "douyin": "抖音",
}

BILIBILI_POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1"
BILIBILI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
BILIBILI_REGION_URL = "https://api.bilibili.com/x/web-interface/ranking/region"
BILIBILI_CATEGORY_RIDS = {
    "all": "0",
    "life": "160",
    "travel": "250",
    "knowledge": "36",
    "food": "211",
    "entertainment": "5",
    "technology": "188",
    "kichiku": "119",
    "music": "3",
    "dance": "129",
    "game": "4",
    "movie": "23",
    "documentary": "177",
}

DOUYIN_HOTSEARCH_URL = "https://aweme.snssdk.com/aweme/v1/hot/search/list/?detail_list=1"
DOUYIN_HOTSEARCH_FALLBACK_URL = (
    "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    "?device_platform=webapp&aid=6383&detail_list=1"
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.toutiao.com/",
}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_chinese_count(value: Any) -> int:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万|亿)?", text)
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "亿":
        number *= 100_000_000
    elif unit == "万":
        number *= 10_000
    return int(number)


def _normalize_zhihu_url(url: Any) -> str:
    text = str(url or "").strip()
    match = re.search(r"questions?/(\d+)", text)
    if match:
        return f"https://www.zhihu.com/question/{match.group(1)}"
    return text


def _request(url: str, referer: str, timeout: int) -> bytes:
    headers = {**REQUEST_HEADERS, "Referer": referer}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _limit(topics: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return topics[:max(1, limit)]


def _filter_topics_by_category(
    topics: list[dict[str, Any]],
    category_key: str | None,
) -> list[dict[str, Any]]:
    """Keep topics whose text matches any keyword of ``category_key``.

    Returns ``topics`` unchanged when the category is empty, ``"all"`` or
    unknown. Otherwise the title/label/desc text is matched case-insensitively
    against the category keywords via substring containment.
    """
    key = str(category_key or "").strip().lower()
    if not key or key == "all":
        return topics
    keywords = [kw.lower() for kw in (CATEGORIES.get(key, {}).get("keywords") or [])]
    if not keywords:
        return topics
    filtered: list[dict[str, Any]] = []
    for topic in topics:
        haystack = " ".join(
            str(topic.get(field) or "")
            for field in ("title", "label", "desc")
        ).lower()
        if any(kw in haystack for kw in keywords):
            filtered.append(topic)
    for index, topic in enumerate(filtered, start=1):
        topic["rank"] = index
    return filtered


def _clean_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return html.unescape(text).strip()


def _normalize_bilibili_url(row: dict[str, Any]) -> str:
    arcurl = str(row.get("arcurl") or row.get("url") or "").strip()
    if arcurl:
        return arcurl.replace("http://", "https://", 1)
    bvid = str(row.get("bvid") or row.get("BVID") or "").strip()
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    aid = row.get("aid") or row.get("aid_v2")
    return f"https://www.bilibili.com/video/av{aid}" if aid else "https://www.bilibili.com"


def _normalize_image_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return "https:" + text
    return text.replace("http://", "https://", 1)


def _parse_duration(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    parts = [int(part) for part in text.split(":") if part.isdigit()]
    if not parts:
        return 0
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def _bilibili_metric(row: dict[str, Any], *keys: str) -> int:
    stat = row.get("stat") if isinstance(row.get("stat"), dict) else {}
    for key in keys:
        if key in stat:
            return _parse_chinese_count(stat.get(key))
        if key in row:
            return _parse_chinese_count(row.get(key))
    return 0


def _normalize_bilibili_row(row: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean_html(row.get("title") or row.get("name"))
    if not title:
        return None
    metrics = {
        "view": _bilibili_metric(row, "view", "play"),
        "like": _bilibili_metric(row, "like"),
        "danmaku": _bilibili_metric(row, "danmaku", "video_review"),
        "favorite": _bilibili_metric(row, "favorite", "favorites"),
        "coin": _bilibili_metric(row, "coin", "coins"),
        "share": _bilibili_metric(row, "share"),
        "reply": _bilibili_metric(row, "reply", "review"),
        "score": _bilibili_metric(row, "score", "pts"),
    }
    owner = row.get("owner") if isinstance(row.get("owner"), dict) else {}
    author = str(owner.get("name") or row.get("author") or row.get("up_name") or "").strip()
    mid = owner.get("mid") or row.get("mid") or row.get("up_id")
    bvid = str(row.get("bvid") or row.get("BVID") or "").strip()
    aid = row.get("aid") or row.get("id")
    cid = row.get("cid")
    category_id = row.get("tid") or row.get("typeid") or row.get("rid")
    category_name = str(row.get("tname") or row.get("typename") or row.get("category") or "").strip()
    cover = _normalize_image_url(row.get("pic") or row.get("cover"))
    desc = _clean_html(row.get("desc") or row.get("description"))
    view = metrics["view"] or _parse_chinese_count(row.get("hot_value"))
    return {
        "rank": 0,
        "title": title,
        "url": _normalize_bilibili_url(row),
        "hot_value": view,
        "label": f"{view} 播放" if view else category_name or "B站视频",
        "source": "B站",
        "type": "video",
        "bvid": bvid,
        "aid": aid,
        "cid": cid,
        "cover": cover,
        "desc": desc,
        "duration": _parse_duration(row.get("duration")),
        "category_id": str(category_id or ""),
        "category_name": category_name,
        "owner": {"name": author, "mid": mid},
        "metrics": metrics,
    }


def _rank_bilibili_topics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topics = [topic for row in rows if (topic := _normalize_bilibili_row(row))]
    topics.sort(key=lambda item: item.get("hot_value") or 0, reverse=True)
    for index, topic in enumerate(topics, start=1):
        topic["rank"] = index
    return topics


def parse_toutiao_hot_board(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Toutiao hot-board JSON into frontend-friendly topic rows."""
    rows = payload.get("data") or []
    topics: list[dict[str, Any]] = []

    for row in rows:
        title = str(row.get("Title") or "").strip()
        if not title:
            continue

        topics.append({
            "rank": len(topics) + 1,
            "title": title,
            "url": str(row.get("Url") or "").strip(),
            "hot_value": _to_int(row.get("HotValue")),
            "label": str(row.get("Label") or "").strip(),
            "source": "今日头条",
        })

    return topics


def parse_zhihu_hot_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Zhihu hot-list JSON into frontend-friendly topic rows."""
    rows = payload.get("data") or []
    topics: list[dict[str, Any]] = []

    for row in rows:
        target = row.get("target") or row.get("question") or {}
        title = str(target.get("title") or row.get("title") or "").strip()
        if not title:
            continue
        detail_text = str(row.get("detail_text") or target.get("detail_text") or "").strip()
        label = str(target.get("excerpt") or row.get("excerpt") or detail_text).strip()
        topics.append({
            "rank": len(topics) + 1,
            "title": title,
            "url": _normalize_zhihu_url(target.get("url") or row.get("url")),
            "hot_value": _parse_chinese_count(detail_text),
            "label": label,
            "source": "知乎",
        })

    return topics


def _extract_xiaohongshu_initial_state(html: str) -> dict[str, Any]:
    marker = "window.__INITIAL_STATE__="
    start = html.find(marker)
    if start < 0:
        return {}
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        end = len(html)
    raw = html[start:end].strip()
    if raw.endswith(";"):
        raw = raw[:-1]
    raw = raw.replace("undefined", "null")
    return json.loads(raw)


def _xiaohongshu_note_id(row: dict[str, Any], note: dict[str, Any]) -> str:
    """Resolve a Xiaohongshu note id, real-id-first across known shapes.

    The Explore ``__INITIAL_STATE__`` feed carries the note id on the *feed row*
    (``row["id"]``), not inside ``noteCard``. The historical ``noteCard.noteId``
    field no longer exists (live HTML shows 0 occurrences), which is why every
    URL used to collapse to the Explore homepage. Probe the row-level id first,
    then any noteCard fallbacks, returning "" only when nothing real is found.
    """
    candidates = [
        row.get("id"),
        row.get("noteId"),
        row.get("note_id"),
        note.get("noteId"),
        note.get("note_id"),
        note.get("id"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        # Skip placeholder rows (e.g. ad/recommend slots) that lack a real id.
        if value and value.lower() not in {"none", "null"}:
            return value
    return ""


def _xiaohongshu_xsec_token(row: dict[str, Any], note: dict[str, Any]) -> str:
    """Resolve the per-note ``xsec_token`` required to open a specific note.

    The token lives at the feed-row level as ``xsecToken`` (camelCase) on the
    Explore feed; older/other shapes spell it ``xsec_token``. It may also be
    nested inside the noteCard. Empty string when absent (caller then omits it).
    """
    candidates = [
        row.get("xsecToken"),
        row.get("xsec_token"),
        note.get("xsecToken"),
        note.get("xsec_token"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value.lower() not in {"none", "null"}:
            return value
    return ""


def _xiaohongshu_note_url(note_id: str, xsec_token: str) -> str:
    """Build a direct Explore note URL, falling back to the homepage only when
    no real note id is available.

    With a token we append ``xsec_token`` + ``xsec_source=pc_feed`` so the link
    opens the concrete note (the explore feed gates note pages behind the
    signed token); without a token we still link to ``/explore/{id}`` which is
    far better than the old always-homepage behaviour.
    """
    if not note_id:
        return "https://www.xiaohongshu.com/explore"
    if xsec_token:
        return (
            f"https://www.xiaohongshu.com/explore/{note_id}"
            f"?xsec_token={quote(xsec_token, safe='')}&xsec_source=pc_feed"
        )
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def _xiaohongshu_feed_rows(state: dict[str, Any]) -> list[Any]:
    """Collect feed rows from every known Explore ``__INITIAL_STATE__`` container.

    Live probing (anonymous, no login) shows the homepage now ships an *empty*
    ``feed.feeds`` and renders notes client-side via a signed homefeed API. But
    several sibling containers carry the same row shape when the page does SSR a
    feed (edge cache / logged-in proxy / category landing): ``feed.feeds``,
    ``feed.feedsWrapper`` and ``feed.placeholderFeeds``. We merge whatever is
    populated (de-duping by row id) so the parser keeps working across shapes
    instead of hard-coding the single, now-frequently-empty ``feeds`` key.
    """
    feed = state.get("feed")
    if not isinstance(feed, dict):
        return []
    rows: list[Any] = []
    seen: set[str] = set()
    for key in ("feeds", "feedsWrapper", "placeholderFeeds"):
        container = feed.get(key)
        if not isinstance(container, list):
            continue
        for row in container:
            if not isinstance(row, dict):
                continue
            note = row.get("noteCard") or row.get("note_card") or {}
            note = note if isinstance(note, dict) else {}
            note_id = _xiaohongshu_note_id(row, note)
            dedup = note_id or id(row)  # fall back to object identity when id-less
            if isinstance(dedup, str) and dedup in seen:
                continue
            if isinstance(dedup, str):
                seen.add(dedup)
            rows.append(row)
    return rows


def _xiaohongshu_valid_id_topics(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Last-resort topics built from ``feed.validIds.noteIds`` (id-only fallback).

    When no row container carries renderable note cards, the homefeed id list
    (``feed.validIds.noteIds``) may still hold real note ids. We turn each into a
    ``/explore/{id}`` topic so the produced URL still points at a *real note*
    (the whole point of the fix) rather than collapsing to the homepage. These
    rows have no title/heat, so they are only used when the card path yields
    nothing and are labelled as plain 推荐笔记.
    """
    feed = state.get("feed")
    if not isinstance(feed, dict):
        return []
    valid_ids = feed.get("validIds")
    note_ids = valid_ids.get("noteIds") if isinstance(valid_ids, dict) else None
    if not isinstance(note_ids, list):
        return []
    topics: list[dict[str, Any]] = []
    for raw_id in note_ids:
        note_id = str(raw_id or "").strip()
        if not note_id or note_id.lower() in {"none", "null"}:
            continue
        topics.append({
            "rank": len(topics) + 1,
            "title": f"小红书推荐笔记 {note_id[:8]}",
            "url": _xiaohongshu_note_url(note_id, ""),
            "hot_value": 0,
            "label": "推荐笔记",
            "source": "小红书",
        })
    return topics


def parse_xiaohongshu_explore_page(html: str) -> list[dict[str, Any]]:
    """Normalize Xiaohongshu Explore initial feed notes into topic rows.

    Xiaohongshu's dedicated hot-search API requires anti-bot headers. For the MVP
    we read the public Explore page's server-rendered ``__INITIAL_STATE__``.

    Key fix: the note id and ``xsec_token`` are read from the *feed row* (the
    current real shape) — ``row["id"]`` + ``row["xsecToken"]`` — NOT from the
    historical ``noteCard.noteId`` (live HTML shows 0 occurrences). That stale
    field was why every URL collapsed to the Explore homepage. With the real
    row-level id (and token when present) the URL now opens the concrete note:
    ``/explore/{id}?xsec_token=...&xsec_source=pc_feed``.

    Rows are gathered from every known SSR container (``feeds`` /
    ``feedsWrapper`` / ``placeholderFeeds``); if none render note cards we fall
    back to ``feed.validIds.noteIds`` so the output still carries real note ids
    rather than homepage links. Returns ``[]`` (never homepage rows) when no real
    note id can be resolved at all.
    """
    state = _extract_xiaohongshu_initial_state(html)
    rows = _xiaohongshu_feed_rows(state)
    topics: list[dict[str, Any]] = []

    for row in rows:
        note = row.get("noteCard") or row.get("note_card") or {}
        if not isinstance(note, dict):
            note = {}
        title = str(note.get("displayTitle") or note.get("title") or "").strip()
        note_id = _xiaohongshu_note_id(row, note)
        # A row is only usable when it yields BOTH a real note id (so the URL is
        # a concrete note, not the homepage) and a title to display.
        if not title or not note_id:
            continue
        xsec_token = _xiaohongshu_xsec_token(row, note)
        liked_count = str((note.get("interactInfo") or {}).get("likedCount") or "").strip()
        topics.append({
            "rank": len(topics) + 1,
            "title": title,
            "url": _xiaohongshu_note_url(note_id, xsec_token),
            "hot_value": _parse_chinese_count(liked_count),
            "label": f"{liked_count}赞" if liked_count else "推荐笔记",
            "source": "小红书",
        })

    # No renderable note cards (anonymous SSR now ships an empty feed): fall back
    # to the id-only list so URLs still point at real notes, never the homepage.
    if not topics:
        topics = _xiaohongshu_valid_id_topics(state)

    return topics


def fetch_toutiao_hot_topics(limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch live hot topics from Toutiao's public hot-board endpoint."""
    raw = _request(TOUTIAO_HOT_BOARD_URL, referer="https://www.toutiao.com/", timeout=timeout)
    payload = json.loads(raw.decode("utf-8"))
    topics = parse_toutiao_hot_board(payload)
    return _limit(topics, limit)


def fetch_zhihu_hot_topics(limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch live hot topics from Zhihu's mobile hot-list endpoint.

    The requested ``limit`` is forwarded to the API ``limit`` query param
    (clamped to 1..100) so over-fetching for category filtering pulls a wider
    list straight from Zhihu.
    """
    url_limit = max(1, min(FETCH_ALL_LIMIT, limit))
    url = ZHIHU_HOT_LIST_URL.format(limit=url_limit)
    raw = _request(url, referer="https://www.zhihu.com/hot", timeout=timeout)
    payload = json.loads(raw.decode("utf-8"))
    topics = parse_zhihu_hot_list(payload)
    return _limit(topics, limit)


def fetch_xiaohongshu_hot_topics(limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch current Xiaohongshu Explore recommendations from public HTML."""
    raw = _request(XIAOHONGSHU_EXPLORE_URL, referer="https://www.xiaohongshu.com/", timeout=timeout)
    html = raw.decode("utf-8", errors="replace")
    topics = parse_xiaohongshu_explore_page(html)
    return _limit(topics, limit)


def _extract_bilibili_rows(payload: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    code = payload.get("code", 0)
    if code != 0:
        raise RuntimeError(f"Bilibili API error: {code} {payload.get('message') or payload.get('msg') or ''}".strip())
    data = payload.get("data") or {}
    if mode == "popular":
        return list(data.get("list") or []) if isinstance(data, dict) else []
    if mode == "search":
        return list(data.get("result") or []) if isinstance(data, dict) else []
    if mode == "region":
        return list(data if isinstance(data, list) else data.get("list") or [])
    return []


def parse_bilibili_popular(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Bilibili popular-list videos and sort by traffic descending."""
    return _rank_bilibili_topics(_extract_bilibili_rows(payload, "popular"))


def parse_bilibili_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Bilibili keyword-search videos and sort by play count."""
    return _rank_bilibili_topics(_extract_bilibili_rows(payload, "search"))


def parse_bilibili_region(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Bilibili region ranking videos and sort by play count."""
    return _rank_bilibili_topics(_extract_bilibili_rows(payload, "region"))


def _bilibili_category_rid(category: str | None) -> str:
    """Resolve a category to a native Bilibili region id, or "" when none.

    A category maps to a native rid when it is listed in
    ``BILIBILI_CATEGORY_RIDS`` or is already a numeric rid. Unified categories
    without a native region (e.g. rural/culture) resolve to "" so callers fall
    back to the popular list + keyword filtering.
    """
    normalized = str(category or "").strip().lower()
    if not normalized or normalized == "all":
        return ""
    if normalized in BILIBILI_CATEGORY_RIDS:
        return BILIBILI_CATEGORY_RIDS[normalized]
    if normalized.isdigit():
        return normalized
    return ""


def fetch_bilibili_hot_topics(
    limit: int = 20,
    timeout: int = 10,
    keyword: str | None = None,
    category: str | None = None,
    sort: str | None = "traffic_desc",
) -> list[dict[str, Any]]:
    """Fetch Bilibili popular/search/region videos as traffic-sorted topics.

    - keyword + optional category: public video search ordered by click/play.
    - category only: public region ranking.
    - neither: public popular list.
    """
    keyword_text = str(keyword or "").strip()
    rid = _bilibili_category_rid(category)
    # Categories without a native Bilibili region (e.g. rural/culture) fall back
    # to the popular list, then keyword-filter on the unified taxonomy.
    category_key = str(category or "").strip().lower()
    filter_after = bool(category_key) and category_key != "all" and not rid and not keyword_text
    if keyword_text:
        params = {
            "search_type": "video",
            "keyword": keyword_text,
            "order": "click",
            "page": 1,
        }
        if rid:
            params["tids"] = rid
        url = f"{BILIBILI_SEARCH_URL}?{urlencode(params)}"
        raw = _request(url, referer="https://search.bilibili.com/", timeout=timeout)
        topics = parse_bilibili_search(json.loads(raw.decode("utf-8")))
    elif rid:
        url = f"{BILIBILI_REGION_URL}?{urlencode({'rid': rid, 'day': 3})}"
        raw = _request(url, referer="https://www.bilibili.com/", timeout=timeout)
        topics = parse_bilibili_region(json.loads(raw.decode("utf-8")))
    else:
        # 热门列表每页 50 条；按 pn 翻页以满足更大的 limit（最多到 100，封顶 4 页）。
        topics = []
        seen_ids: set[Any] = set()
        max_pages = min(4, max(1, (int(limit) + 49) // 50))
        for pn in range(1, max_pages + 1):
            page_url = f"https://api.bilibili.com/x/web-interface/popular?ps=50&pn={pn}"
            try:
                raw = _request(page_url, referer="https://www.bilibili.com/v/popular/all", timeout=timeout)
                page_topics = parse_bilibili_popular(json.loads(raw.decode("utf-8")))
            except Exception:
                if pn == 1:
                    raise  # 首页错误照常抛出（与单次抓取一致，含 API code error）
                break  # 仅后续页失败时优雅停止，保留已取到的

            if not page_topics:
                break
            for item in page_topics:
                key = item.get("bvid") or item.get("url")
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                topics.append(item)
            if len(topics) >= int(limit):
                break
    if filter_after:
        topics = _filter_topics_by_category(topics, category_key)
    if sort == "traffic_desc":
        topics.sort(key=lambda item: item.get("hot_value") or 0, reverse=True)
        for index, topic in enumerate(topics, start=1):
            topic["rank"] = index
    return _limit(topics, limit)


DOUYIN_LABEL_TEXT = {1: "新", 3: "热", 8: "沸", 5: "荐", 9: "首发"}


def _douyin_label(raw_label: Any, hot_value: int) -> str:
    """Map Douyin's hot-board label to display text.

    The board's `label` field is a status code (int), not free text. Keep a
    genuine non-numeric string if present; map known codes to 热/新/沸; else
    fall back to a hot-value badge.
    """
    text = str(raw_label or "").strip()
    if text and not text.lstrip("-").isdigit():
        return text
    code = _to_int(raw_label, default=0)
    if code in DOUYIN_LABEL_TEXT:
        return DOUYIN_LABEL_TEXT[code]
    return f"{hot_value} 热度"


def _douyin_topic_url(sentence_id: Any, word: str) -> str:
    sid = str(sentence_id or "").strip()
    if sid and sid != "0":
        return f"https://www.douyin.com/hot/{sid}"
    return f"https://www.douyin.com/search/{quote(word)}"


def parse_douyin_hot_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Douyin hot-search board JSON into B站-shaped topic rows.

    Preserves the official hot-board ordering (word_list position) as rank.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    topics: list[dict[str, Any]] = []
    seen: set[Any] = set()

    # 抖音免签热榜每个列表上限约 50；合并 word_list + trending_list + recommend_list
    # 并按 sentence_id/group_id/word 去重，尽量多榨出唯一热点（仍受平台 ~50-55 上限约束）。
    for list_key in ("word_list", "trending_list", "recommend_list"):
        rows = data.get(list_key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            word = str(row.get("word") or "").strip()
            if not word:
                continue
            dedup_key = row.get("sentence_id") or row.get("group_id") or word
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            hot_value = _to_int(row.get("hot_value"))
            word_cover = row.get("word_cover") if isinstance(row.get("word_cover"), dict) else {}
            url_list = word_cover.get("url_list") if isinstance(word_cover.get("url_list"), list) else []
            cover = _normalize_image_url(url_list[0]) if url_list else ""
            topics.append({
                "rank": len(topics) + 1,
                "title": word,
                "url": _douyin_topic_url(row.get("sentence_id"), word),
                "hot_value": hot_value,
                "label": _douyin_label(row.get("label"), hot_value),
                "source": "抖音",
                "type": "video",
                "cover": cover,
                "desc": "",
                "metrics": {
                    "hot_value": hot_value,
                    "video_count": _to_int(row.get("video_count")),
                    "discuss_video_count": _to_int(row.get("discuss_video_count")),
                },
            })

    return topics


def fetch_douyin_hot_topics(
    limit: int = 20,
    timeout: int = 10,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the Douyin hot-search board as B站-shaped topics (primary + fallback).

    Douyin exposes no sign-free search API, so a non-empty keyword filters the
    board by case-insensitive substring match on the topic title (word).
    """
    referer = "https://www.douyin.com/"
    payload: dict[str, Any] | None = None
    errors: list[str] = []
    for url in (DOUYIN_HOTSEARCH_URL, DOUYIN_HOTSEARCH_FALLBACK_URL):
        try:
            raw = _request(url, referer=referer, timeout=timeout)
            candidate = json.loads(raw.decode("utf-8"))
            data = candidate.get("data") if isinstance(candidate.get("data"), dict) else {}
            if data.get("word_list"):
                payload = candidate
                break
            errors.append(f"{url}: empty word_list")
        except Exception as exc:  # noqa: BLE001 - try fallback before failing
            errors.append(f"{url}: {exc}")
            continue
    if payload is None:
        raise RuntimeError("抖音热搜接口请求失败：" + " | ".join(errors))

    topics = parse_douyin_hot_search(payload)
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        needle = keyword_text.lower()
        topics = [topic for topic in topics if needle in str(topic.get("title") or "").lower()]
        for index, topic in enumerate(topics, start=1):
            topic["rank"] = index
    return _limit(topics, limit)


def fetch_hot_topics(
    source: str = "toutiao",
    limit: int = 20,
    timeout: int = 10,
    keyword: str | None = None,
    category: str | None = None,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    normalized = (source or "toutiao").strip().lower()

    # Bilibili keeps its native region/search dispatch (best quality); the
    # over-fetch + keyword fallback for rid-less categories lives inside
    # fetch_bilibili_hot_topics.
    if normalized in {"bilibili", "b站", "哔哩哔哩", "bili"}:
        return fetch_bilibili_hot_topics(limit=limit, timeout=timeout, keyword=keyword, category=category, sort=sort)

    # Every other source: over-fetch the natural list, apply the unified
    # category keyword filter, then truncate to the user's limit. category/sort
    # are NOT forwarded to fetch_* helpers that do not accept them.
    if normalized in {"toutiao", "今日头条"}:
        topics = fetch_toutiao_hot_topics(limit=FETCH_ALL_LIMIT, timeout=timeout)
    elif normalized in {"zhihu", "知乎"}:
        topics = fetch_zhihu_hot_topics(limit=FETCH_ALL_LIMIT, timeout=timeout)
    elif normalized in {"xiaohongshu", "xhs", "小红书"}:
        topics = fetch_xiaohongshu_hot_topics(limit=FETCH_ALL_LIMIT, timeout=timeout)
    elif normalized in {"douyin", "抖音", "dy"}:
        topics = fetch_douyin_hot_topics(limit=FETCH_ALL_LIMIT, timeout=timeout, keyword=keyword)
    else:
        raise ValueError(f"不支持的数据源：{source}")

    topics = _filter_topics_by_category(topics, category)
    return _limit(topics, limit)
