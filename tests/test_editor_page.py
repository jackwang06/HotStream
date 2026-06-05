from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_legacy_file(name: str) -> str:
    """Read a production-served frontend file.

    The active delivery is Next.js serving ``web/legacy/`` (authed legacy route);
    the Python server also serves the same directory at its root. These tests
    assert against the REAL served files (previously they read the stale ``ui/``
    copy, which diverged from production).
    """
    return (PROJECT_ROOT / "web" / "legacy" / name).read_text(encoding="utf-8")


# ── Editor (WYSIWYG, Markdown-backed) ──────────────────────────────────────

def test_editor_is_wysiwyg_markdown_backed():
    content = read_legacy_file("editor.html")
    assert "HotStream 文案编辑器" in content
    # The preview itself is the editable surface (所见即所得).
    assert "previewDoc" in content
    assert "contenteditable" in content
    # Markdown block model + conversion bridges.
    assert "markdownToBlocks" in content
    assert "blocksToMarkdown" in content


def test_editor_uses_local_vendored_libs():
    content = read_legacy_file("editor.html")
    assert "/vendor/marked.min.js" in content
    assert "turndown" in content
    assert "html2canvas" in content


def test_editor_export_and_draft_keys():
    content = read_legacy_file("editor.html")
    assert 'id="exportImageBtn"' in content
    assert "导出长图" in content
    assert "hotstream.editorDraft" in content
    assert "hotstream.editorLiveDraft" in content


# ── Home: edit / draft handoff ─────────────────────────────────────────────

def test_home_edit_and_draft_entries():
    content = read_legacy_file("index.html")
    assert 'id="editContentBtn"' in content
    assert "生成后编辑内容" in content
    assert 'id="continueDraftBtn"' in content
    assert "继续编辑草稿" in content
    assert "hotstream.editorDraft" in content
    assert "hotstream.editorLiveDraft" in content


def test_home_topic_rows_open_original_link_in_new_tab():
    content = read_legacy_file("index.html")
    assert 'class="topic-link"' in content
    assert 'target="_blank"' in content
    assert 'rel="noopener noreferrer"' in content
    assert "event.stopPropagation()" in content


def test_home_uses_poetic_campaign_title():
    content = read_legacy_file("index.html")
    assert "前山如画，四季成歌" in content


# ── Home: data sources, category filter, count ─────────────────────────────

def test_home_has_all_sources_category_and_count():
    content = read_legacy_file("index.html")
    assert 'value="bilibili"' in content
    assert 'value="douyin"' in content       # 抖音 source
    assert 'value="custom"' in content        # 自定义链接 source
    assert 'id="bilibiliCategory"' in content  # unified category dropdown
    assert 'id="limitInput"' in content        # configurable count (1-100)
    assert "params.set('category'" in content


def test_home_custom_source_url_parsing():
    content = read_legacy_file("index.html")
    assert 'id="customUrl"' in content
    assert "parseCustomBtn" in content
    assert "/api/custom-source" in content


def test_home_generation_and_qwen_flow():
    content = read_legacy_file("index.html")
    assert "/api/hot-topics" in content
    assert "/api/analyze-video" in content
    assert "/api/generate-copy" in content
    assert "qwen_analysis" in content
    assert "前山牧场四季牧歌" in content
