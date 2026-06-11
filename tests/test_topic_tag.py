"""热点类别 tag：派生、补全、接入响应与生成提示。"""
import json
from unittest.mock import patch

from hotstream import copywriter, server
from hotstream.scraper import classify_topic_tag, tag_topics


def test_classify_topic_tag_by_keywords():
    assert classify_topic_tag({"title": "城里火锅探店"}) == "美食"
    assert classify_topic_tag({"title": "内蒙古草原旅游攻略"}) == "出行·旅行"  # 旅游/攻略 先于 草原
    assert classify_topic_tag({"title": "牧民草原放牧日常"}) == "乡村·三农"
    assert classify_topic_tag({"title": "非遗民俗展演"}) == "文化·民俗"
    assert classify_topic_tag({"title": "无法归类的随机新闻"}) == ""


def test_classify_uses_label_and_desc():
    assert classify_topic_tag({"title": "某视频", "desc": "记录草原牧场的牛羊"}) == "乡村·三农"


def test_tag_topics_adds_field_and_preserves_existing():
    topics = [{"title": "火锅美食节"}, {"title": "旅游攻略", "tag": "用户自定义"}]
    tag_topics(topics)
    assert topics[0]["tag"] == "美食"
    assert topics[1]["tag"] == "用户自定义"  # 已有非空不覆盖


def test_hot_topics_response_includes_tag():
    with patch("hotstream.server.fetch_hot_topics", return_value=[{"title": "草原牧场骑马"}]):
        _s, _h, body = server.build_hot_topics_response(source="toutiao")
    payload = json.loads(body.decode("utf-8"))
    assert payload["topics"][0]["tag"] == "乡村·三农"


def test_generation_prompt_includes_tag():
    prompt = copywriter.build_default_temporary_prompt(topic={"title": "草原游", "tag": "出行·旅行"})
    assert "内容类别：出行·旅行" in prompt


def test_generation_prompt_omits_tag_when_absent():
    prompt = copywriter.build_default_temporary_prompt(topic={"title": "草原游"})
    assert "内容类别" not in prompt
