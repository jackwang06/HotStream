from pathlib import Path

from hotstream.scenic_profile import DEFAULT_SCENIC_PROFILE_SLUG, load_scenic_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_qianshan_siji_muge_profile_documents_exist():
    profile_dir = PROJECT_ROOT / "scenic_profiles" / "qianshan-siji-muge"

    assert (profile_dir / "overview.md").exists()
    assert (profile_dir / "advantages.md").exists()
    assert (profile_dir / "nearby-attractions.md").exists()
    assert (profile_dir / "writing-rules.md").exists()


def test_load_default_scenic_profile_combines_core_documents():
    profile = load_scenic_profile()

    assert profile.slug == DEFAULT_SCENIC_PROFILE_SLUG
    assert profile.name == "前山牧场四季牧歌民俗风情园"
    assert "平均海拔约 2400 米" in profile.content
    assert "乃楞格尔草原" in profile.content
    assert "团建研学" in profile.content
    assert "禁止编造" in profile.content
    assert len(profile.documents) >= 4
