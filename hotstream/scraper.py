from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

TOUTIAO_HOT_BOARD_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
ZHIHU_HOT_LIST_URL = "https://api.zhihu.com/topstory/hot-list?limit=50&reverse_order=0"
XIAOHONGSHU_EXPLORE_URL = "https://www.xiaohongshu.com/explore"

SOURCE_LABELS = {
    "toutiao": "今日头条",
    "zhihu": "知乎",
    "xiaohongshu": "小红书",
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


def fetch_hot_topics(source: str = "toutiao", limit: int = 20, timeout: int = 10) -> list[dict[str, Any]]:
    normalized = (source or "toutiao").strip().lower()
    if normalized in {"toutiao", "今日头条"}:
        return fetch_toutiao_hot_topics(limit=limit, timeout=timeout)
    if normalized in {"zhihu", "知乎"}:
        return fetch_zhihu_hot_topics(limit=limit, timeout=timeout)
    if normalized in {"xiaohongshu", "xhs", "小红书"}:
        return fetch_xiaohongshu_hot_topics(limit=limit, timeout=timeout)
    raise ValueError(f"不支持的数据源：{source}")
