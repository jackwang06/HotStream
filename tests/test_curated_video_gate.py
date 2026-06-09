"""精选热点(curated)视频分析行为的回归测试。

演进：
1) 初版 bug：B站/抖音 精选条目被视频门控死锁（强制分析却无分析入口）。
   → 修复：精选条目 curated=true；selectedHasVideo() 对 curated 短路 false（不再强制分析）。
2) 二版诉求：视频类精选条目应能“可选”分析视频（像普通流程那样，但不强制）。
   → canAnalyzeVideo() 成为“能否分析”的权威判定，纳入视频类精选(B站/抖音且有封面)；
     选中视频类精选时显示分析面板；分析结果带入生成；新闻类精选隐藏面板直接生成。
3) 连带修复：60s 静默自动刷新不再冲掉精选列表（curatedActive 守卫）。

所有断言基于 web/legacy/index.html 源码字符串（与既有测试同风格）。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_legacy(name: str) -> str:
    return (PROJECT_ROOT / "web" / "legacy" / name).read_text(encoding="utf-8")


# ── 基础：精选条目标记 + 不被强制分析 ──────────────────────────────────────
def test_curated_entries_are_marked():
    assert "t.curated = true" in _read_legacy("index.html")


def test_curated_not_forced_to_analyze():
    """selectedHasVideo()（“是否必须分析”）对 curated 短路返回 false。"""
    assert "if (selectedTopic.curated) return false;" in _read_legacy("index.html")


# ── 可选分析：视频类精选可分析，新闻类不可 ──────────────────────────────────
def test_has_cover_helper_exists():
    assert "function hasCoverForAnalysis" in _read_legacy("index.html")


def test_can_analyze_includes_curated_video():
    """canAnalyzeVideo() 纳入“视频类精选(B站/抖音且有封面)”。"""
    content = _read_legacy("index.html")
    assert "selectedTopic.curated" in content
    assert "hasCoverForAnalysis(selectedTopic)" in content


def test_analyze_button_gate_no_longer_blocks_curated():
    """分析按钮门控只看 canAnalyzeVideo()，不再用 selectedHasVideo() 误拦精选。"""
    content = _read_legacy("index.html")
    assert "if (!selectedTopic || !canAnalyzeVideo()) {" in content
    # 旧的会拦死精选的写法必须已移除
    assert "!canAnalyzeVideo() || !selectedHasVideo()" not in content


def test_curated_selection_toggles_panel_by_analyzability():
    """选中精选条目时按 canAnalyzeVideo() 决定是否显示视频面板。"""
    content = _read_legacy("index.html")
    assert "videoAnalysisPanel.classList.toggle('hidden', !analyzable)" in content


# ── 连带：60s 静默刷新不冲掉精选 ────────────────────────────────────────────
def test_curated_active_guard_against_silent_refresh():
    content = _read_legacy("index.html")
    assert "let curatedActive = false;" in content
    assert "curatedActive = true;" in content
    assert "if (silent && curatedActive) return;" in content


def test_fetch_hot_topics_drops_curated_ghost():
    """手动抓热榜时丢弃残留 curated 选择（现为代码块形式）。"""
    content = _read_legacy("index.html")
    assert "if (selectedTopic && selectedTopic.curated) {" in content
    assert "if (!silent) curatedActive = false;" in content


# ── 回归：真实视频源仍要求先分析 ────────────────────────────────────────────
def test_real_video_source_still_requires_analysis():
    content = _read_legacy("index.html")
    assert "['B站', '抖音'].includes(selectedTopic.source)" in content
    assert "请先用 Qwen 分析所选视频" in content
