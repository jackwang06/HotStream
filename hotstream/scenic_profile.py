from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENIC_PROFILES_DIR = PROJECT_ROOT / "scenic_profiles"
DEFAULT_SCENIC_PROFILE_SLUG = "qianshan-siji-muge"
DEFAULT_SCENIC_PROFILE_NAME = "前山牧场四季牧歌民俗风情园"
_PROFILE_DOC_ORDER = [
    "overview.md",
    "advantages.md",
    "nearby-attractions.md",
    "writing-rules.md",
]


@dataclass(frozen=True)
class ScenicProfile:
    slug: str
    name: str
    content: str
    documents: dict[str, str]


def _read_profile_documents(profile_dir: Path) -> dict[str, str]:
    documents: dict[str, str] = {}
    ordered = [profile_dir / name for name in _PROFILE_DOC_ORDER]
    extras = sorted(path for path in profile_dir.glob("*.md") if path.name not in _PROFILE_DOC_ORDER)
    for path in [*ordered, *extras]:
        if path.exists():
            documents[path.name] = path.read_text(encoding="utf-8").strip()
    return documents


def load_scenic_profile(slug: str = DEFAULT_SCENIC_PROFILE_SLUG) -> ScenicProfile:
    """Load the scenic-profile knowledge base used by every generated post."""
    normalized = (slug or DEFAULT_SCENIC_PROFILE_SLUG).strip() or DEFAULT_SCENIC_PROFILE_SLUG
    profile_dir = SCENIC_PROFILES_DIR / normalized
    if not profile_dir.exists():
        raise FileNotFoundError(f"景点画像不存在：{normalized}")
    documents = _read_profile_documents(profile_dir)
    if not documents:
        raise FileNotFoundError(f"景点画像目录没有 Markdown 文档：{profile_dir}")
    content = "\n\n".join(f"## {name}\n\n{text}" for name, text in documents.items())
    return ScenicProfile(
        slug=normalized,
        name=DEFAULT_SCENIC_PROFILE_NAME if normalized == DEFAULT_SCENIC_PROFILE_SLUG else normalized,
        content=content,
        documents=documents,
    )


def scenic_profile_prompt_section(slug: str = DEFAULT_SCENIC_PROFILE_SLUG) -> str:
    profile = load_scenic_profile(slug)
    return (
        f"固定宣传对象：{profile.name}\n"
        "以下是景点画像资料。所有推文都必须围绕该景点做自然宣传，不要偏离为泛热点评论。\n\n"
        f"{profile.content}"
    )
