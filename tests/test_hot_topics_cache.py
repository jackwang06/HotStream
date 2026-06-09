"""热点抓取进程内 TTL 缓存（hotstream.server.fetch_hot_topics_cached）的测试。

全部离线：patch ``hotstream.server.fetch_hot_topics``（缓存包装内部调用的名字），
用计数器断言真实抓取被调用的次数。
"""
import time
from unittest.mock import patch

from hotstream import server


def _counting_fetch(payload, counter):
    def _f(source, **kwargs):
        counter["n"] += 1
        return [dict(item) for item in payload]
    return _f


def test_cache_hit_within_ttl():
    """TTL 内同参数重复请求只真实抓取一次。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        r1 = server.fetch_hot_topics_cached("toutiao", limit=5)
        r2 = server.fetch_hot_topics_cached("toutiao", limit=5)
    assert counter["n"] == 1
    assert r1 == r2 == [{"title": "A"}]


def test_cache_miss_after_ttl_expiry():
    """TTL 过期后重新抓取。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.fetch_hot_topics_cached("toutiao", limit=5, ttl=0.05)
        time.sleep(0.08)
        server.fetch_hot_topics_cached("toutiao", limit=5, ttl=0.05)
    assert counter["n"] == 2


def test_distinct_params_are_separate_entries():
    """不同 source/limit/category 是不同缓存条目。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.fetch_hot_topics_cached("toutiao", limit=5)
        server.fetch_hot_topics_cached("toutiao", limit=6)
        server.fetch_hot_topics_cached("toutiao", limit=5, category="travel")
        server.fetch_hot_topics_cached("zhihu", limit=5)
    assert counter["n"] == 4


def test_none_kwargs_share_entry_with_absent():
    """keyword/category/sort 为 None 时等同未指定，与“只传 limit”命中同一条。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.fetch_hot_topics_cached("toutiao", limit=5)
        server.fetch_hot_topics_cached("toutiao", limit=5, keyword=None, category=None, sort=None)
    assert counter["n"] == 1


def test_mutation_does_not_pollute_cache():
    """调用方改动返回值（加 rank / 覆盖字段 / append）不污染缓存。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        r1 = server.fetch_hot_topics_cached("toutiao", limit=5)
        r1[0]["title"] = "MUTATED"
        r1[0]["rank"] = 99
        r1.append({"title": "EXTRA"})
        r2 = server.fetch_hot_topics_cached("toutiao", limit=5)
    assert counter["n"] == 1
    assert r2 == [{"title": "A"}]


def test_ttl_zero_bypasses_cache():
    """ttl<=0 直接透传，不缓存。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.fetch_hot_topics_cached("toutiao", limit=5, ttl=0)
        server.fetch_hot_topics_cached("toutiao", limit=5, ttl=0)
    assert counter["n"] == 2


def test_clear_cache_forces_refetch():
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.fetch_hot_topics_cached("toutiao", limit=5)
        server.clear_hot_topics_cache()
        server.fetch_hot_topics_cached("toutiao", limit=5)
    assert counter["n"] == 2


def test_failure_is_not_cached():
    """抓取失败不写缓存，下次仍会重试。"""
    counter = {"n": 0}

    def _flaky(source, **kwargs):
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("boom")
        return [{"title": "ok"}]

    with patch("hotstream.server.fetch_hot_topics", _flaky):
        try:
            server.fetch_hot_topics_cached("toutiao", limit=5)
        except RuntimeError:
            pass
        result = server.fetch_hot_topics_cached("toutiao", limit=5)
    assert counter["n"] == 2
    assert result == [{"title": "ok"}]


def test_build_hot_topics_response_uses_cache():
    """集成：build_hot_topics_response 同参数重复调用走缓存（真实抓取一次）。"""
    counter = {"n": 0}
    with patch("hotstream.server.fetch_hot_topics", _counting_fetch([{"title": "A"}], counter)):
        server.build_hot_topics_response(source="toutiao", limit=5)
        server.build_hot_topics_response(source="toutiao", limit=5)
    assert counter["n"] == 1
