from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_ui_file(name: str) -> str:
    return (PROJECT_ROOT / "ui" / name).read_text(encoding="utf-8")


def test_editor_page_exists_with_core_editor_regions():
    content = read_ui_file("editor.html")

    assert "HotStream 文案编辑器" in content
    assert "id=\"editorText\"" in content
    assert "id=\"blockEditor\"" in content
    assert "id=\"materialGrid\"" in content
    assert "id=\"exportImageBtn\"" in content
    assert "导出长图" in content


def test_home_page_has_prominent_edit_and_draft_entries():
    content = read_ui_file("index.html")

    assert "id=\"editContentBtn\"" in content
    assert "生成后编辑内容" in content
    assert "id=\"continueDraftBtn\"" in content
    assert "继续编辑草稿" in content
    assert "hotstream.editorDraft" in content
    assert "hotstream.editorLiveDraft" in content
    assert "editor.html" in content


def test_home_topic_rows_have_original_link_icon_opening_new_tab():
    content = read_ui_file("index.html")

    assert "class=\"topic-link\"" in content
    assert "target=\"_blank\"" in content
    assert "rel=\"noopener noreferrer\"" in content
    assert "aria-label=\"打开原文链接" in content
    assert "↗" in content
    assert "event.stopPropagation()" in content
    assert "<button class=\"topic\"" not in content
    assert "role=\"button\"" in content
    assert "tabindex=\"0\"" in content


def test_editor_uses_visual_blocks_instead_of_markdown_image_codes():
    content = read_ui_file("editor.html")

    assert "id=\"blockEditor\"" in content
    assert "draggable=\"true\"" in content
    assert "data-block-type=\"image\"" in content
    assert "moveBlock" in content
    assert "insertImageBlock" in content
    assert "Markdown 图片行" not in content


def test_editor_removes_low_value_divider_action_and_adds_draft_import():
    content = read_ui_file("editor.html")

    assert "insertDividerBtn" not in content
    assert "插入分隔" not in content
    assert "id=\"loadDraftBtn\"" in content
    assert "载入本地草稿" in content
    assert "下次从主页点“继续编辑草稿”" in content


def test_home_page_uses_poetic_campaign_title_not_literal_workflow_copy():
    content = read_ui_file("index.html")

    assert "前山如画，四季成歌" in content
    assert "抓热点，给前山牧场四季牧歌写推文。" not in content


def test_home_page_has_bilibili_video_controls_and_qwen_flow():
    content = read_ui_file("index.html")

    assert 'value="bilibili"' in content
    assert "B站视频" in content
    assert 'id="bilibiliCategory"' in content
    assert 'id="qwenApiKey"' in content
    assert "/api/settings" in content
    assert "loadServerSettings" in content
    assert 'id="videoAnalysisOutput"' in content
    assert "/api/analyze-video" in content
    assert "qwen_analysis" in content
    assert "source_images" in content
    assert "前山牧场四季牧歌" in content


def test_editor_preview_height_aligns_with_editor_work_area():
    content = read_ui_file("editor.html")

    assert "--editor-work-area-height: calc(100vh - 382px);" in content
    assert ".block-editor" in content
    assert "min-height: var(--editor-work-area-height);" in content
    assert ".preview-wrap" in content
    assert "height: 620px" not in content


def test_home_page_bilibili_query_is_sent_to_backend_not_only_local_filter():
    content = read_ui_file("index.html")

    assert "params.set('keyword'" in content
    assert "params.set('category'" in content
    assert "params.set('sort', 'traffic_desc')" in content
    assert "bilibiliCategory.value" in content
    assert "/api/hot-topics?${params.toString()}" in content
