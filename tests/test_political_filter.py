"""政治脱敏：词库判定、热点过滤、生成提示注入、三链路接通的测试。

重点同时验证两件事：① 命中无歧义政治词的热点被剔除；② **不误杀文旅营销内容**
（裸地名 新疆/西藏、县长推介、督察组检查、那达慕等不应被过滤——这些词刻意不在词库）。
"""
import json
from unittest.mock import patch

from hotstream import copywriter, server
from hotstream.political_filter import filter_political_topics, is_political


# ── 词库判定：政治命中 ──────────────────────────────────────────────────────
def test_is_political_hits_unambiguous_terms():
    for text in [
        "国务院发布新规定", "全国人大会议召开", "台独势力受挫", "普京会见外宾",
        "联合国安理会决议", "中央纪委通报", "一国两制方针", "解放军演习",
    ]:
        assert is_political(text), text


# ── 词库判定：文旅营销内容**不**误杀（关键）─────────────────────────────────
def test_is_political_does_not_flag_travel_marketing():
    for text in [
        "新疆伊犁草原旅游攻略",          # 裸地名，旅游目的地
        "西藏林芝桃花节开幕",            # 裸地名
        "县长直播带货推介前山牧场",      # 县长(已剔除)
        "镇长推介古镇民俗游",            # 镇长(已剔除)
        "环保督察组检查景区整改",        # 督察组(已剔除)
        "草原那达慕大会牛羊成群",        # 纯文旅
        "二十四节气民俗美食节",          # 纯文旅
        "脱贫攻坚带动乡村旅游",          # 脱贫攻坚办(已剔除), 乡村振兴正面
        "抗战纪念馆红色旅游研学",        # 战争(已剔除)
    ]:
        assert not is_political(text), text


def test_filter_political_topics_removes_only_political():
    topics = [
        {"title": "前山牧场草原音乐节"},
        {"title": "国务院常务会议召开"},
        {"title": "新疆喀纳斯秋色"},
        {"title": "台独分子被制裁", "desc": "涉及分裂国家"},
    ]
    kept = [t["title"] for t in filter_political_topics(topics)]
    assert "前山牧场草原音乐节" in kept
    assert "新疆喀纳斯秋色" in kept
    assert "国务院常务会议召开" not in kept
    assert "台独分子被制裁" not in kept


def test_filter_checks_desc_and_label_fields():
    topics = [{"title": "某视频", "desc": "内容涉及军事冲突", "label": ""}]
    assert filter_political_topics(topics) == []  # desc 命中也剔除


# ── 生成提示注入 ────────────────────────────────────────────────────────────
def test_build_deepseek_messages_injects_desensitize_instruction():
    msgs = copywriter.build_deepseek_messages(topic={"title": "x"}, political_filter=True)
    system = " ".join(m["content"] for m in msgs if m["role"] == "system")
    assert "政治脱敏" in system and "严禁涉及任何政治" in system


def test_build_deepseek_messages_no_instruction_when_off():
    msgs = copywriter.build_deepseek_messages(topic={"title": "x"}, political_filter=False)
    system = " ".join(m["content"] for m in msgs if m["role"] == "system")
    assert "政治脱敏" not in system


def test_ai_assist_messages_inject_desensitize_when_on():
    """AI帮写(扩写/缩写/改写/补充)开启脱敏时也注入硬约束（不留绕过缺口）。"""
    for mode in ["expand", "condense", "rewrite", "supplement"]:
        msgs = copywriter.build_ai_assist_messages(
            mode=mode, selected_text="一段文案", requirement="改一下", political_filter=True
        )
        system = " ".join(m["content"] for m in msgs if m["role"] == "system")
        assert "政治脱敏" in system, mode


def test_ai_assist_messages_no_inject_when_off():
    msgs = copywriter.build_ai_assist_messages(mode="expand", selected_text="一段文案", political_filter=False)
    system = " ".join(m["content"] for m in msgs if m["role"] == "system")
    assert "政治脱敏" not in system


# ── 三链路接通（server）─────────────────────────────────────────────────────
def _hot(source, political):
    status, _h, body = server.build_hot_topics_response(source=source, political=political)
    return status, json.loads(body.decode("utf-8"))


def test_hot_topics_response_filters_when_political_on():
    topics = [{"title": "草原旅游攻略"}, {"title": "全国人大代表议案"}]
    with patch("hotstream.server.fetch_hot_topics", return_value=topics):
        _s, on = _hot("toutiao", True)
        _s2, off = _hot("toutiao", False)
    on_titles = [t["title"] for t in on["topics"]]
    off_titles = [t["title"] for t in off["topics"]]
    assert "草原旅游攻略" in on_titles and "全国人大代表议案" not in on_titles
    assert "全国人大代表议案" in off_titles  # 关闭时不过滤


def test_curated_response_filters_aggregated_pool():
    pool = [{"title": "牧场四季牧歌"}, {"title": "国务院召开常务会议"}]

    def _fake_fetch(source, **kwargs):
        return pool if source == "toutiao" else []

    captured = {}

    def _fake_select(topics, **kwargs):
        captured["seen"] = [t["title"] for t in topics]
        return topics

    body_in = json.dumps({"api_key": "sk", "political_filter": True}).encode("utf-8")
    with patch("hotstream.server.fetch_hot_topics", side_effect=_fake_fetch), \
         patch("hotstream.server.select_relevant_topics", side_effect=_fake_select):
        server.build_curated_topics_response(body_in)
    # 涉政热点在聚合后被剔除，select_relevant_topics 根本看不到它
    assert "牧场四季牧歌" in captured["seen"]
    assert "国务院召开常务会议" not in captured["seen"]


def test_copy_response_threads_political_flag():
    captured = {}

    def _fake_generate(**kwargs):
        captured.update(kwargs)
        return "文案"

    body_in = json.dumps({
        "topic": {"title": "草原"}, "api_key": "sk", "political_filter": True,
    }).encode("utf-8")
    with patch("hotstream.server.generate_copy_with_deepseek", side_effect=_fake_generate), \
         patch("hotstream.server.fetch_related_images", return_value=[]):
        server.build_copy_response(body_in)
    assert captured.get("political_filter") is True
