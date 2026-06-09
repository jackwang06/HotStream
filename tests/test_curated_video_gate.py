"""精选热点(curated)视频门控修复的回归测试。

Bug：来自 B站/抖音 的精选条目（source="B站"/"抖音"）选中后点「生成文案」会被
视频分析门控拦死（"请先用 Qwen 分析所选视频"），但精选场景没有视频分析入口 → 死锁。

修复（web/legacy/index.html）：
1. 精选条目标记 t.curated=true；
2. selectedHasVideo() 对 selectedTopic.curated 短路返回 false（跳过视频门控）；
3. 进入精选模式隐藏视频面板 + 清残留分析；
4. fetchHotTopics 丢弃残留的 curated 幽灵选择，避免悬挂引用送后端；
5. 回归保护：真实 B站/抖音 下拉源仍要求先分析视频。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_legacy(name: str) -> str:
    return (PROJECT_ROOT / "web" / "legacy" / name).read_text(encoding="utf-8")


def test_curated_entries_are_marked():
    """每个精选条目必须打上 curated 标记，门控才能识别。"""
    content = _read_legacy("index.html")
    assert "t.curated = true" in content


def test_selected_has_video_short_circuits_for_curated():
    """selectedHasVideo() 必须对 curated 条目短路返回 false。"""
    content = _read_legacy("index.html")
    assert "if (selectedTopic.curated) return false;" in content


def test_curated_mode_hides_video_panel():
    """进入精选模式时隐藏视频分析面板，避免下拉框停在视频源时面板残留。"""
    content = _read_legacy("index.html")
    assert "videoAnalysisPanel.classList.add('hidden')" in content


def test_fetch_hot_topics_drops_curated_ghost():
    """刷新热点时丢弃残留的 curated 选择，避免把过期幽灵 topic 送往后端。"""
    content = _read_legacy("index.html")
    assert "if (selectedTopic && selectedTopic.curated) selectedTopic = null;" in content


def test_real_video_source_still_requires_analysis():
    """回归：真实 B站/抖音 源（无 curated 标记）仍走视频门控、仍要求先分析。"""
    content = _read_legacy("index.html")
    assert "['B站', '抖音'].includes(selectedTopic.source)" in content
    assert "请先用 Qwen 分析所选视频" in content
