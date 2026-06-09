"""视频内容推断管线的测试：联网检索(web_search) + DeepSeek 还原(copywriter) +
analyze-video 编排(server) + 编辑文本注入生成(_format_qwen_analysis)。

全部离线：HTTP / DeepSeek / Qwen 调用均被 patch，无真实网络。
"""
import json
from unittest.mock import patch

import pytest

from hotstream import copywriter, server, web_search


# ── 联网检索 web_search ────────────────────────────────────────────────────
def test_search_baidu_parses_titles():
    page = '<h3 class="t"><a href="x">牧场风光美如画</a></h3><h3><a>二十四节气看蒙牛</a></h3>'
    with patch("hotstream.web_search._http_get_text", return_value=page):
        out = web_search.search_baidu("牧场", 5, 8)
    assert any("牧场风光美如画" == x["title"] for x in out)
    assert all(x["source"] == "百度" for x in out)


def test_search_toutiao_parses_embedded_json():
    page = '{"title":"现代牧业塞北牧场","abstract":"走进牧场看牛粪变黄金"}'
    with patch("hotstream.web_search._http_get_text", return_value=page):
        out = web_search.search_toutiao("牧场", 5, 8)
    assert out and out[0]["title"] == "现代牧业塞北牧场"
    assert out[0]["abstract"].startswith("走进牧场")


def test_search_toutiao_unescapes_unicode():
    # 标题需 >=4 字才不被噪声过滤；草原牧场风光 的 \\uXXXX 形式。
    page = '{"title":"\\u8349\\u539f\\u7267\\u573a\\u98ce\\u5149","abstract":""}'
    with patch("hotstream.web_search._http_get_text", return_value=page):
        out = web_search.search_toutiao("x", 5, 8)
    assert out and out[0]["title"] == "草原牧场风光"


def test_search_web_snippets_aggregates_and_degrades():
    with patch("hotstream.web_search.search_baidu", return_value=[{"source": "百度", "title": "A", "abstract": ""}]), \
         patch("hotstream.web_search.search_toutiao", return_value=[]), \
         patch("hotstream.web_search.search_zhihu", side_effect=RuntimeError("blocked")):
        res = web_search.search_web_snippets("query")
    assert res["sources_hit"] == ["百度"]          # 头条空、知乎异常都被跳过
    assert len(res["snippets"]) == 1


def test_search_web_snippets_empty_query_short_circuits():
    res = web_search.search_web_snippets("")
    assert res == {"snippets": [], "sources_hit": []}


def test_search_web_snippets_dedupes_by_title():
    with patch("hotstream.web_search.search_baidu", return_value=[{"source": "百度", "title": "同标题", "abstract": ""}]), \
         patch("hotstream.web_search.search_toutiao", return_value=[{"source": "头条", "title": "同标题", "abstract": "x"}]), \
         patch("hotstream.web_search.search_zhihu", return_value=[]):
        res = web_search.search_web_snippets("q")
    assert len(res["snippets"]) == 1


# ── DeepSeek 还原 restore_topic_full_picture ───────────────────────────────
class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_restore_topic_full_picture_returns_text():
    payload = {"choices": [{"message": {"content": "推断：这是讲草原牧场四季的视频。"}}]}
    with patch("hotstream.copywriter.urlopen", return_value=_FakeResp(payload)):
        text = copywriter.restore_topic_full_picture(
            "牧场视频", "B站", "封面是草原",
            [{"source": "百度", "title": "t", "abstract": "a"}], api_key="sk",
        )
    assert "草原牧场四季" in text


def test_restore_requires_api_key():
    with pytest.raises(RuntimeError):
        copywriter.restore_topic_full_picture("t", "B站", "o", [], api_key="")


def test_restore_messages_include_snippets_and_overview():
    msgs = copywriter._build_video_restore_messages(
        "标题X", "抖音", "概况文本",
        [{"source": "头条", "title": "碎片标题", "abstract": "碎片摘要"}],
    )
    user = msgs[-1]["content"]
    assert "概况文本" in user and "碎片标题" in user and "碎片摘要" in user


# ── 编辑文本注入生成 _format_qwen_analysis ─────────────────────────────────
def test_format_qwen_uses_edited_text_verbatim():
    out = copywriter._format_qwen_analysis({"edited_text": "用户改过的视频内容"})
    assert "用户改过的视频内容" in out
    assert "视频内容推断" in out


def test_format_qwen_uses_inferred_key():
    out = copywriter._format_qwen_analysis({"inferred": "DeepSeek 还原文本"})
    assert "DeepSeek 还原文本" in out


def test_format_qwen_falls_back_to_structured_fields():
    out = copywriter._format_qwen_analysis({"summary": "结构化概述"})
    assert "Qwen2.5-VL 视频分析" in out
    assert "结构化概述" in out


# ── analyze-video 编排 build_video_analysis_response ───────────────────────
def _run(raw: dict):
    status, _headers, body = server.build_video_analysis_response(json.dumps(raw).encode("utf-8"))
    return status, json.loads(body.decode("utf-8"))


def test_build_video_analysis_full_pipeline():
    topic = {"title": "牧场视频", "source": "B站", "cover": "http://x/c.jpg"}
    with patch("hotstream.server.analyze_video_with_qwen",
               return_value={"analysis": {"summary": "草原"}, "raw_text": "封面是草原牧场", "images": []}), \
         patch("hotstream.server.search_web_snippets",
               return_value={"snippets": [{"source": "百度", "title": "t", "abstract": "a"}], "sources_hit": ["百度", "头条"]}), \
         patch("hotstream.server.restore_topic_full_picture",
               return_value="推断：这是讲草原牧场四季的视频。"):
        status, payload = _run({"topic": topic, "api_key": "qwen", "deepseek_api_key": "sk-ds"})
    assert status == 200 and payload["success"] is True
    assert "草原牧场四季" in payload["inferred"]
    assert payload["sources_hit"] == ["百度", "头条"]


def test_build_video_analysis_degrades_without_deepseek_key():
    topic = {"title": "牧场视频", "source": "B站"}
    with patch("hotstream.server.analyze_video_with_qwen",
               return_value={"analysis": {"summary": "草原"}, "raw_text": "封面概况", "images": []}), \
         patch("hotstream.server.search_web_snippets") as mock_search, \
         patch("hotstream.server.restore_topic_full_picture") as mock_restore:
        status, payload = _run({"topic": topic, "api_key": "qwen"})  # 无 deepseek_api_key
    assert status == 200
    assert payload["inferred"] == "" and payload["sources_hit"] == []
    mock_search.assert_not_called()
    mock_restore.assert_not_called()


def test_build_video_analysis_restore_failure_still_200():
    topic = {"title": "牧场视频", "source": "B站"}
    with patch("hotstream.server.analyze_video_with_qwen",
               return_value={"analysis": {}, "raw_text": "概况", "images": []}), \
         patch("hotstream.server.search_web_snippets", return_value={"snippets": [], "sources_hit": []}), \
         patch("hotstream.server.restore_topic_full_picture", side_effect=RuntimeError("ds down")):
        status, payload = _run({"topic": topic, "api_key": "qwen", "deepseek_api_key": "sk"})
    assert status == 200
    assert payload["inferred"] == ""  # 还原失败 → 降级, 仍 200 返回 Qwen 概况


def test_build_video_analysis_qwen_failure_502():
    with patch("hotstream.server.analyze_video_with_qwen", side_effect=RuntimeError("qwen boom")):
        status, payload = _run({"topic": {"title": "x"}, "api_key": "qwen", "deepseek_api_key": "sk"})
    assert status == 502 and payload["success"] is False
