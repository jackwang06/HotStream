from __future__ import annotations

import html
import json
import re
import urllib.request
from typing import Any
from urllib.parse import urlencode

TOUTIAO_HOT_BOARD_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
ZHIHU_HOT_LIST_URL = "https://api.zhihu.com/topstory/hot-list?limit=50&reverse_order=0"
XIAOHONGSHU_EXPLORE_URL = "https://www.xiaohongshu.com/explore"

SOURCE_LABELS = {
    "toutiao": "今日头条",
    "zhihu": "知乎",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
}

BILIBILI_POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1"
BILIBILI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
BILIBILI_REGION_URL = "https://api.bilibili.com/x/web-interface/ranking/region"
BILIBILI_CATEGORY_RIDS = {
    "all": "0",
    "life": "160",
    "travel": "96",
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


def parse_xiaohongshu_explore_page(html: str) -> list[dict[str, Any]]:
    """Normalize Xiaohongshu Explore initial feed notes into topic rows.

    Xiaohongshu's dedicated hot-search API requires anti-bot headers. For the MVP,
    we use the public Explore page's server-rendered initial feed as a stable
    no-login source of currently recommended high-engagement notes.
    """
    state = _extract_xiaohongshu_initial_state(html)
    rows = ((state.get("feed") or {}).get("feeds") or [])
    topics: list[dict[str, Any]] = []

    for row in rows:
        note = row.get("noteCard") or row.get("note_card") or {}
        title = str(note.get("displayTitle") or note.get("title") or "").strip()
        if not title:
            continue
        note_id = str(note.get("noteId") or note.get("id") or "").strip()
        liked_count = str((note.get("interactInfo") or {}).get("likedCount") or "").strip()
        topics.append({
            "rank": len(topics) + 1,
            "title": title,
            "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "https://www.xiaohongshu.com/explore",
            "hot_value": _parse_chinese_count(liked_count),
            "label": f"{liked_count}赞" if liked_count else "推荐笔记",
            "source": "小红书",
        })

    return topics


def fetch_toutiao_hot_topics(limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch live hot topics from Toutiao's public hot-board endpoint."""
    raw = _request(TOUTIAO_HOT_BOARD_URL, referer="https://www.toutiao.com/", timeout=timeout)
    payload = json.loads(raw.decode("utf-8"))
    topics = parse_toutiao_hot_board(payload)
    return _limit(topics, limit)


def fetch_zhihu_hot_topics(limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch live hot topics from Zhihu's mobile hot-list endpoint."""
    raw = _request(ZHIHU_HOT_LIST_URL, referer="https://www.zhihu.com/hot", timeout=timeout)
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
    normalized = str(category or "").strip().lower()
    if not normalized or normalized == "all":
        return ""
    return BILIBILI_CATEGORY_RIDS.get(normalized, normalized)


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
        raw = _request(BILIBILI_POPULAR_URL, referer="https://www.bilibili.com/v/popular/all", timeout=timeout)
        topics = parse_bilibili_popular(json.loads(raw.decode("utf-8")))
    if sort == "traffic_desc":
        topics.sort(key=lambda item: item.get("hot_value") or 0, reverse=True)
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
    if normalized in {"toutiao", "今日头条"}:
        return fetch_toutiao_hot_topics(limit=limit, timeout=timeout)
    if normalized in {"zhihu", "知乎"}:
        return fetch_zhihu_hot_topics(limit=limit, timeout=timeout)
    if normalized in {"xiaohongshu", "xhs", "小红书"}:
        return fetch_xiaohongshu_hot_topics(limit=limit, timeout=timeout)
    if normalized in {"bilibili", "b站", "哔哩哔哩", "bili"}:
        return fetch_bilibili_hot_topics(limit=limit, timeout=timeout, keyword=keyword, category=category, sort=sort)
    raise ValueError(f"不支持的数据源：{source}")
