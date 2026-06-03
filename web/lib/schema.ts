// Canonical DB schema (single source of truth, used by the migration runner).
// All objects live in the `wangyafei` schema because the DB user has rights
// ONLY there (no `public`). Idempotent: safe to run repeatedly.
export const SCHEMA_SQL = `
-- ── Users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wangyafei.users (
    id                   SERIAL PRIMARY KEY,
    username             TEXT NOT NULL UNIQUE,
    password_hash        TEXT NOT NULL,
    display_name         TEXT NOT NULL DEFAULT '',
    role                 TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Sessions (opaque token; cookie holds the raw token, we store its SHA-256) ──
CREATE TABLE IF NOT EXISTS wangyafei.sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES wangyafei.users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id    ON wangyafei.sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON wangyafei.sessions(expires_at);

-- ── Per-user settings (1:1 with users) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS wangyafei.user_settings (
    user_id          INTEGER PRIMARY KEY REFERENCES wangyafei.users(id) ON DELETE CASCADE,
    deepseek_api_key TEXT NOT NULL DEFAULT '',
    qwen_api_key     TEXT NOT NULL DEFAULT '',
    global_prompt    TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Drafts / history: ensure they exist (legacy Python layer may have made
--    them already), then add per-user scoping. We deliberately DO NOT add a
--    NOT NULL constraint on user_id yet (the legacy Python service may still
--    write key-less rows); non-null is enforced in the application layer.
CREATE TABLE IF NOT EXISTS wangyafei.drafts (
    id             SERIAL PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '',
    content_blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
    images         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS wangyafei.history (
    id          SERIAL PRIMARY KEY,
    topic_title TEXT NOT NULL DEFAULT '',
    copy_text   TEXT NOT NULL DEFAULT '',
    hot_value   TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',
    chars       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── user_settings: per-class custom API endpoint/model (empty string = use
--    runtime default). text_* = 文案生成 API, video_* = 视频分析 API.
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS text_api_url    TEXT NOT NULL DEFAULT '';
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS text_api_model  TEXT NOT NULL DEFAULT '';
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS video_api_url   TEXT NOT NULL DEFAULT '';
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS video_api_model TEXT NOT NULL DEFAULT '';
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS default_prompt  TEXT NOT NULL DEFAULT '';

-- ── Named prompt presets (per-user). Users may create/edit/rename/delete an
--    unlimited number; the one referenced by user_settings.active_preset_id is
--    the currently selected one (the starting point for the homepage prompt).
CREATE TABLE IF NOT EXISTS wangyafei.prompt_presets (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES wangyafei.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prompt_presets_user_id ON wangyafei.prompt_presets(user_id);

-- The currently selected preset for each user (NULL = none; falls back to the
-- legacy user_settings.default_prompt column). ON DELETE SET NULL keeps the
-- column consistent when a preset is removed.
ALTER TABLE wangyafei.user_settings ADD COLUMN IF NOT EXISTS active_preset_id INTEGER REFERENCES wangyafei.prompt_presets(id) ON DELETE SET NULL;

ALTER TABLE wangyafei.drafts  ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES wangyafei.users(id) ON DELETE RESTRICT;
ALTER TABLE wangyafei.history ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES wangyafei.users(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_drafts_user_id  ON wangyafei.drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_history_user_id ON wangyafei.history(user_id);

-- ── Shared knowledge base (GLOBAL, not per-user). Any logged-in user can add &
--    view all entries; editing/deleting/enabling is restricted (creator or admin,
--    enforced in the application layer). Enabled entries are auto-injected into
--    the AI copy-generation context.
CREATE TABLE IF NOT EXISTS wangyafei.knowledge_base (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_by  INTEGER REFERENCES wangyafei.users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_enabled    ON wangyafei.knowledge_base(enabled);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_created_by ON wangyafei.knowledge_base(created_by);
`;
