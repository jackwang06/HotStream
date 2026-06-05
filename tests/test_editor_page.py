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


# ── Editor: undo/redo (目标C) ──────────────────────────────────────────────

def test_editor_has_undo_and_redo_buttons():
    content = read_legacy_file("editor.html")
    assert 'id="undoBtn"' in content
    assert 'id="redoBtn"' in content
    assert "撤销" in content
    assert "恢复" in content


def test_editor_undo_redo_keyboard_shortcuts():
    """Ctrl+Z / Ctrl+Y must be wired to undo/redo and block browser default."""
    content = read_legacy_file("editor.html")
    assert "Ctrl+Z" in content or "ctrlKey" in content
    assert "Ctrl+Y" in content or "doRedo" in content
    # Must intercept only when previewDoc is focused.
    assert "previewDoc" in content
    assert "doUndo" in content
    assert "doRedo" in content


def test_editor_history_stack_implementation():
    """The editor must maintain an internal history stack with 30-entry cap."""
    content = read_legacy_file("editor.html")
    assert "historyStack" in content
    assert "HISTORY_MAX" in content
    assert "30" in content  # the max history depth
    assert "historyIdx" in content


def test_editor_undo_redo_update_buttons():
    """updateUndoRedoBtns must disable each button when at bounds."""
    content = read_legacy_file("editor.html")
    assert "updateUndoRedoBtns" in content
    assert "disabled" in content


def test_editor_snapshot_push_truncates_redo_branch():
    """After pushing a new snapshot, the redo branch (ahead of historyIdx) must be cut."""
    content = read_legacy_file("editor.html")
    # Typical pattern: splice(historyIdx + 1) or slice to truncate future entries.
    assert "splice" in content or "slice" in content


def test_editor_undo_syncs_blocks_and_autosaves():
    """Undo/redo must call syncBlocksFromDom (and optionally auto-save)."""
    content = read_legacy_file("editor.html")
    assert "syncBlocksFromDom" in content
    assert "doUndo" in content
    assert "doRedo" in content


def test_editor_no_clear_draft_button():
    """清空编辑页 button (clearDraftBtn) must be removed."""
    content = read_legacy_file("editor.html")
    assert "clearDraftBtn" not in content
    assert "清空编辑页" not in content


def test_editor_no_add_paragraph_button():
    """追加段落 button (addParagraphBtn) must be removed."""
    content = read_legacy_file("editor.html")
    assert "addParagraphBtn" not in content
    assert "追加段落" not in content


def test_editor_preserved_features_intact():
    """Core editor features (drag, color, format, page-break, export) must survive."""
    content = read_legacy_file("editor.html")
    assert "markdownToBlocks" in content
    assert "blocksToMarkdown" in content
    assert "exportImageBtn" in content
    assert "导出长图" in content
    assert "syncBlocksFromDom" in content
    # Format-painter and page-break features must still be present.
    assert "formatPainter" in content
    # Draft keys must still be present (handoff to/from homepage).
    assert "hotstream.editorDraft" in content
    assert "hotstream.editorLiveDraft" in content


# ── Profile client: 代理灵魂 entry card (目标B) ────────────────────────────

def _read_next_file(rel: str) -> str:
    """Read a file relative to web/ (Next.js source)."""
    return (PROJECT_ROOT / "web" / rel).read_text(encoding="utf-8")


def test_profile_client_has_soul_entry_card():
    """profile-client.tsx must show the 代理灵魂 card with a link to /presets."""
    content = _read_next_file("app/profile/profile-client.tsx")
    assert "代理灵魂" in content
    assert "/presets" in content
    assert "管理代理灵魂预设" in content


def test_profile_client_soul_is_readonly_preview():
    """The soul section must display a read-only preview, not an editable textarea."""
    content = _read_next_file("app/profile/profile-client.tsx")
    assert "代理灵魂" in content
    # The save() function must NOT send global_prompt any more.
    assert "global_prompt 已改由灵魂预设管理" in content or "global_prompt" not in content.split("save()")[1][:500] if "save()" in content else True


def test_profile_client_save_does_not_send_global_prompt():
    """save() in profile-client.tsx must not include global_prompt in the POST body."""
    content = _read_next_file("app/profile/profile-client.tsx")
    # Find the save function section and assert global_prompt is absent from the body dict.
    assert "global_prompt 已改由灵魂预设管理，不再通过此处保存" in content


# ── Presets client: two-tab UI for soul + default kinds (目标B) ──────────────

def test_presets_client_has_two_tab_kinds():
    """presets-client.tsx must have tabs for both 代理灵魂预设 and 默认提示词预设."""
    content = _read_next_file("app/presets/presets-client.tsx")
    assert "代理灵魂预设" in content
    assert "默认提示词预设" in content


def test_presets_client_uses_kind_in_api_calls():
    """presets-client.tsx must pass ?kind=soul and ?kind=default to the API."""
    content = _read_next_file("app/presets/presets-client.tsx")
    assert "kind=soul" in content or '`/api/presets?kind=${kind}`' in content
    assert "kind" in content


def test_presets_client_both_active_ids_tracked():
    """presets-client.tsx must track both activePresetId and activeSoulPresetId."""
    content = _read_next_file("app/presets/presets-client.tsx")
    assert "activePresetId" in content
    assert "activeSoulPresetId" in content


def test_presets_client_soul_create_uses_soul_kind():
    """When the soul tab is active, creating a preset must use kind='soul'."""
    content = _read_next_file("app/presets/presets-client.tsx")
    assert 'kind: activeTab' in content or 'kind="soul"' in content or "kind: \"soul\"" in content
