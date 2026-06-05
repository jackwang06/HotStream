"""
Tests for the 代理灵魂（agent soul）multi-preset feature.

Scope:
- Python constants (hotstream.copywriter.DEFAULT_GLOBAL_PROMPT) stay stable and are
  used correctly by build_deepseek_messages when Next.js passes a soul as global_prompt.
- The TypeScript SOULS constant file (web/lib/prompts.ts) contains the expected four
  named presets with the correct content anchors.
- All four soul contents share a common fabrication-guard clause.
- The schema.ts migration SQL is idempotent and includes both the kind column and the
  active_soul_preset_id FK column.
- The seed-admin.ts script imports SOULS and wires the ensureSoulPresets helper.
- The users API route wires the soul preset seeding for new accounts.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hotstream.copywriter import (
    DEFAULT_GLOBAL_PROMPT,
    MARKDOWN_OUTPUT_INSTRUCTION,
    build_deepseek_messages,
    generate_copy_with_deepseek,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _read_web_file(rel: str) -> str:
    return (PROJECT_ROOT / "web" / rel).read_text(encoding="utf-8")


# ── 1. Python DEFAULT_GLOBAL_PROMPT stays stable ─────────────────────────────


def test_default_global_prompt_is_copywriter_soul():
    """The Python default soul is the 资深文案主笔 persona used for years."""
    assert "资深中文新媒体文案主笔" in DEFAULT_GLOBAL_PROMPT
    assert "不是写作顾问" in DEFAULT_GLOBAL_PROMPT
    assert "禁止编造" in DEFAULT_GLOBAL_PROMPT
    assert "不要把推测写成事实" in DEFAULT_GLOBAL_PROMPT


def test_default_global_prompt_matches_ts_default_soul():
    """web/lib/prompts.ts DEFAULT_GLOBAL_PROMPT must equal Python's constant."""
    ts_content = _read_web_file("lib/prompts.ts")
    # The TS file exports DEFAULT_GLOBAL_PROMPT; its value should contain the
    # same signature phrases as the Python constant.
    assert "资深中文新媒体文案主笔" in ts_content
    assert "不是写作顾问" in ts_content
    assert "禁止编造" in ts_content
    assert "不要把推测写成事实" in ts_content


# ── 2. build_deepseek_messages correctly uses soul as system prompt ────────────


def test_build_deepseek_messages_soul_as_global_prompt():
    """When Next.js injects a soul preset as global_prompt, Python uses it verbatim as system."""
    soul_content = (
        "你是一个软萌可爱的中文新媒体文案写手，为「前山牧场四季牧歌民俗风情园」写种草推文。"
        "直接输出成稿，禁止编造未提供的时间、地点、价格、活动、成绩、采访等事实；"
        "事实不足时围绕氛围、心情和向往展开，不把推测写成事实。"
    )
    messages = build_deepseek_messages(
        topic={"title": "草原露营热", "source": "小红书", "hot_value": 10000},
        brief="软萌风格推文",
        global_prompt=soul_content,
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == soul_content + MARKDOWN_OUTPUT_INSTRUCTION
    # User message should contain topic material
    assert "草原露营热" in messages[1]["content"]


def test_build_deepseek_messages_dignified_soul_as_global_prompt():
    """庄重 soul is also accepted as global_prompt without any change."""
    soul = (
        "你是一位庄重大气的中文文案主笔，为「前山牧场四季牧歌民俗风情园」撰写宣传文案。"
        "直接输出成稿，不把推测写成事实。"
    )
    messages = build_deepseek_messages(
        topic={"title": "文化旅游节", "source": "人民日报", "hot_value": 5000},
        brief="",
        global_prompt=soul,
    )
    assert messages[0]["content"] == soul + MARKDOWN_OUTPUT_INSTRUCTION


def test_generate_copy_with_deepseek_soul_forwarded_as_system():
    """generate_copy_with_deepseek sends the soul as the system message body."""
    soul = "你是一个热情活泼的中文新媒体文案写手，直接输出成稿，不把推测写成事实。"
    captured = {}

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "活泼风格文案"}}]}).encode()

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp()

    with patch("hotstream.copywriter.urlopen", fake_urlopen):
        result = generate_copy_with_deepseek(
            topic={"title": "草原露营热"},
            brief="",
            api_key="sk-test",
            global_prompt=soul,
        )

    assert result == "活泼风格文案"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][0]["content"] == soul + MARKDOWN_OUTPUT_INSTRUCTION


# ── 3. SOULS TypeScript constant has all four presets with correct content ────


def test_ts_souls_constant_has_four_named_presets():
    """web/lib/prompts.ts exports SOULS with the four factory presets."""
    ts = _read_web_file("lib/prompts.ts")
    assert 'name: "默认"' in ts
    assert 'name: "可爱"' in ts
    assert 'name: "庄重"' in ts
    assert 'name: "活泼"' in ts


def test_ts_souls_cute_content_anchors():
    """可爱 soul has the expected content anchors."""
    ts = _read_web_file("lib/prompts.ts")
    assert "软萌可爱" in ts
    assert "语气词（呀/啦/哦/呐）" in ts


def test_ts_souls_dignified_content_anchors():
    """庄重 soul has the expected content anchors."""
    ts = _read_web_file("lib/prompts.ts")
    assert "庄重大气" in ts
    assert "格调高雅" in ts
    assert "人文价值" in ts


def test_ts_souls_lively_content_anchors():
    """活泼 soul has the expected content anchors."""
    ts = _read_web_file("lib/prompts.ts")
    assert "热情活泼" in ts
    assert "有画面感和号召力" in ts


def test_all_souls_contain_fabrication_guard():
    """Every soul preset content must include a fabrication-guard phrase.

    「默认」uses "不要把推测写成事实" (the original DEFAULT_GLOBAL_PROMPT phrasing);
    the other three use "不把推测写成事实". Both forms are equivalent guards.
    """
    ts = _read_web_file("lib/prompts.ts")
    # Count both the short and long forms of the guard.
    count_short = ts.count("不把推测写成事实")          # 可爱/庄重/活泼
    count_long  = ts.count("不要把推测写成事实")        # 默认
    total = count_short + count_long
    assert total >= 4, (
        f"Expected ≥4 fabrication-guard occurrences across all four souls, "
        f"got short={count_short} long={count_long}"
    )


def test_all_souls_mandate_direct_output():
    """Each soul should instruct the model to output the article directly (成稿)."""
    ts = _read_web_file("lib/prompts.ts")
    count = ts.count("直接输出成稿")
    # 可爱/庄重/活泼 all say 直接输出成稿; 默认 says 直接输出一篇推文正文
    assert count >= 3, f"Expected ≥3 souls with '直接输出成稿', got {count}"


def test_ts_souls_default_equals_default_global_prompt():
    """The TS SOULS[0] default content mirrors the Python DEFAULT_GLOBAL_PROMPT."""
    ts = _read_web_file("lib/prompts.ts")
    # The TS default soul is explicitly set to DEFAULT_GLOBAL_PROMPT
    assert "content: DEFAULT_GLOBAL_PROMPT" in ts or 'name: "默认", content: DEFAULT_GLOBAL_PROMPT' in ts


# ── 4. Schema SQL includes kind column and active_soul_preset_id FK ────────────


def test_schema_sql_has_kind_column_for_presets():
    """schema.ts must include the ALTER TABLE adding the kind column (idempotent)."""
    ts = _read_web_file("lib/schema.ts")
    assert "kind" in ts
    assert "ADD COLUMN IF NOT EXISTS kind" in ts
    assert "DEFAULT 'default'" in ts


def test_schema_sql_has_active_soul_preset_id_column():
    """schema.ts must include the active_soul_preset_id column on user_settings."""
    ts = _read_web_file("lib/schema.ts")
    assert "active_soul_preset_id" in ts
    assert "ADD COLUMN IF NOT EXISTS active_soul_preset_id" in ts
    # ON DELETE SET NULL must be present to preserve consistency when preset deleted.
    assert "ON DELETE SET NULL" in ts


def test_schema_sql_both_kind_columns_are_idempotent():
    """Both kind and active_soul_preset_id use ADD COLUMN IF NOT EXISTS (idempotent)."""
    ts = _read_web_file("lib/schema.ts")
    add_if_not_exists_count = ts.count("ADD COLUMN IF NOT EXISTS")
    # At minimum: kind, active_soul_preset_id, plus the other already-existing columns
    assert add_if_not_exists_count >= 2


# ── 5. lib/presets.ts exposes required functions ──────────────────────────────


def test_presets_ts_exports_getActiveSoulContent():
    """lib/presets.ts must export getActiveSoulContent for the Next.js routes."""
    ts = _read_web_file("lib/presets.ts")
    assert "getActiveSoulContent" in ts
    assert "active_soul_preset_id" in ts


def test_presets_ts_listPresets_returns_both_active_ids():
    """listPresets returns both activePresetId and activeSoulPresetId."""
    ts = _read_web_file("lib/presets.ts")
    assert "activePresetId" in ts
    assert "activeSoulPresetId" in ts


def test_presets_ts_setActivePreset_dispatches_by_kind():
    """setActivePreset must look up the kind and write the correct column."""
    ts = _read_web_file("lib/presets.ts")
    assert "active_soul_preset_id" in ts
    assert "active_preset_id" in ts
    assert "kind" in ts


# ── 6. API routes wired correctly ────────────────────────────────────────────


def test_generate_copy_route_injects_soul():
    """web/app/api/generate-copy/route.ts must call getActiveSoulContent and forward soul."""
    ts = _read_web_file("app/api/generate-copy/route.ts")
    assert "getActiveSoulContent" in ts
    assert "soul" in ts
    assert "payload.global_prompt = soul" in ts


def test_settings_route_returns_effective_soul_as_global_prompt():
    """web/app/api/settings/route.ts must return the effective soul as global_prompt."""
    ts = _read_web_file("app/api/settings/route.ts")
    assert "getActiveSoulContent" in ts
    assert "global_prompt" in ts
    assert "effectiveSoul" in ts


def test_presets_route_supports_kind_query_param():
    """web/app/api/presets/route.ts must read the ?kind= query param."""
    ts = _read_web_file("app/api/presets/route.ts")
    assert "kind" in ts
    assert 'soul' in ts
    assert "kindFromSearch" in ts or "searchParams" in ts or 'get("kind")' in ts


# ── 7. Seed scripts wire soul preset creation ─────────────────────────────────


def test_seed_admin_imports_souls_and_seeds_them():
    """web/scripts/seed-admin.ts must import SOULS and call ensureSoulPresets."""
    ts = _read_web_file("scripts/seed-admin.ts")
    assert "SOULS" in ts
    assert "ensureSoulPresets" in ts
    assert 'kind: "soul"' in ts or "kind='soul'" in ts or '"soul"' in ts


def test_users_api_seeds_soul_presets_on_create():
    """web/app/api/users/route.ts must seed soul presets when creating a new user."""
    ts = _read_web_file("app/api/users/route.ts")
    assert "SOULS" in ts
    # Must call createPreset with kind='soul' or equivalent
    assert "soul" in ts
