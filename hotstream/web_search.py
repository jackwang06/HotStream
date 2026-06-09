"""联网检索：用关键词在百度/头条/知乎搜相关图文标题与摘要（best-effort）。

用于"视频内容还原"管线的第 2 步：拿 Qwen 给出的概况/标题去各平台搜具体信息，
把零散摘要交给 DeepSeek 综合还原热点全貌。每个源都是尽力而为——抓不到/被风控就
跳过，绝不阻断整条流程；调用方据 ``sources_hit`` 知道实际命中了哪些源。

注意：匿名网页搜索本身脆弱（HTML 结构变动、风控、需登录态），百度通常最稳，
头条次之，知乎匿名经常拿不到。所以结果是"有多少用多少"，并明确标注来源。
"""
from __future__ import annotations

import gzip
import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def _http_get_text(url: str, timeout: int, referer: str = "") -> str:
    headers = dict(_SEARCH_HEADERS)
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError):
                # 个别站点误标 Content-Encoding: gzip；解压失败就按原始字节处理。
                pass
    return raw.decode("utf-8", "ignore")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _json_unescape(value: str) -> str:
    """把从内嵌 JSON 正则里抓到的字符串安全反转义（处理 \\uXXXX / \\" / \\\\）。

    页面已按 UTF-8 解码，故字面中文无需再动；只有真含 JSON 转义时才需还原。
    用 json.loads 包一层引号即可正确处理两种情况；失败则原样返回。
    """
    try:
        return json.loads('"' + value + '"')
    except Exception:
        return value


def _dedupe_by_title(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for it in items:
        key = it.get("title", "")
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def search_baidu(query: str, limit: int, timeout: int) -> list[dict[str, str]]:
    """百度网页搜索：抓结果标题（best-effort，结构脆弱）。"""
    try:
        page = _http_get_text(
            f"https://www.baidu.com/s?wd={quote(query)}&rn=10",
            timeout,
            "https://www.baidu.com/",
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    # 结果标题：<h3 ...><a ...>TITLE</a></h3>
    for m in re.finditer(r"<h3[^>]*>\s*<a[^>]*>(.*?)</a>", page, re.S):
        title = _clean(m.group(1))
        if len(title) >= 4:
            out.append({"source": "百度", "title": title, "abstract": ""})
        if len(out) >= limit:
            break
    return out


def search_toutiao(query: str, limit: int, timeout: int) -> list[dict[str, str]]:
    """头条搜索：优先结果页里内嵌 JSON 的标题/摘要，退化到 HTML 标题。"""
    try:
        page = _http_get_text(
            f"https://so.toutiao.com/search?dvpf=pc&source=input&keyword={quote(query)}",
            timeout,
            "https://so.toutiao.com/",
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    # 内嵌 JSON 里常见 "title":"..." 与 "abstract":"..."
    titles = re.findall(r'"title"\s*:\s*"((?:[^"\\]|\\.){4,200})"', page)
    abstracts = re.findall(r'"abstract"\s*:\s*"((?:[^"\\]|\\.){0,300})"', page)
    for i, raw_title in enumerate(titles):
        title = _clean(_json_unescape(raw_title))
        if len(title) < 4:
            continue
        abstract = ""
        if i < len(abstracts):
            abstract = _clean(_json_unescape(abstracts[i]))[:200]
        out.append({"source": "头条", "title": title, "abstract": abstract})
        if len(out) >= limit:
            break
    return out


def search_zhihu(query: str, limit: int, timeout: int) -> list[dict[str, str]]:
    """知乎搜索 API（匿名常被风控，best-effort）。"""
    try:
        raw = _http_get_text(
            f"https://www.zhihu.com/api/v4/search_v3?t=general&q={quote(query)}&correction=1&limit=10",
            timeout,
            "https://www.zhihu.com/search",
        )
        data = json.loads(raw)
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for item in (data.get("data") or []):
        obj = item.get("object") or {}
        title = _clean(obj.get("title") or obj.get("question", {}).get("name") or "")
        excerpt = _clean(obj.get("excerpt") or obj.get("content") or "")[:200]
        if len(title) >= 4:
            out.append({"source": "知乎", "title": title, "abstract": excerpt})
        if len(out) >= limit:
            break
    return out


def search_web_snippets(
    query: str,
    sources: tuple[str, ...] = ("百度", "头条", "知乎"),
    per_source: int = 5,
    timeout: int = 6,
) -> dict[str, Any]:
    """聚合各源搜索结果。返回 ``{snippets:[{source,title,abstract}], sources_hit:[...]}``。

    三源**并发**抓取（墙钟≈最慢单源，而非三者相加），避免串行吃掉上游代理超时预算；
    每个源独立 best-effort，任一异常/为空都跳过，不影响其它源与整体流程。
    分派表在函数内构造，以便引用当前模块函数（单测 patch 各 search_* 才生效）。
    """
    providers = {"百度": search_baidu, "头条": search_toutiao, "知乎": search_zhihu}
    query = (query or "").strip()
    if not query:
        return {"snippets": [], "sources_hit": []}
    selected = [(name, providers[name]) for name in sources if name in providers]
    if not selected:
        return {"snippets": [], "sources_hit": []}

    def _safe(provider) -> list[dict[str, str]]:
        try:
            return provider(query, per_source, timeout) or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        # executor.map 保序：返回顺序与 selected 一致，以维持稳定的 sources_hit 顺序。
        results = list(executor.map(lambda nf: _safe(nf[1]), selected))

    snippets: list[dict[str, str]] = []
    sources_hit: list[str] = []
    for (name, _provider), got in zip(selected, results):
        if got:
            sources_hit.append(name)
            snippets.extend(got)
    return {"snippets": _dedupe_by_title(snippets), "sources_hit": sources_hit}
