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
