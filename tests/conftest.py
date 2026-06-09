"""全局测试夹具。

热点抓取新增了进程内 TTL 缓存（hotstream.server）。为避免缓存在用例间串味
（前一个用例 patch 的抓取结果被后一个用例命中），每个测试前后都清空它。
"""
import pytest

from hotstream.server import clear_hot_topics_cache


@pytest.fixture(autouse=True)
def _isolate_hot_topics_cache():
    clear_hot_topics_cache()
    yield
    clear_hot_topics_cache()
