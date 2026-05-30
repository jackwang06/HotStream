from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import psycopg2
import psycopg2.extras


def _load_dotenv() -> None:
    """Load .env from the project root if present."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _env(key: str) -> str:
    value = os.environ.get(key, "")
    if not value and key == "DB_HOST":
        # optionally fall back to .env reading
        pass
    return value


@dataclass
class SettingsRow:
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    global_prompt: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DraftRow:
    id: int | None = None
    title: str = ""
    content_blocks: str = "[]"  # JSON string
    images: str = "[]"  # JSON string
    created_at: str = ""
    updated_at: str = ""


@dataclass
class HistoryRow:
    id: int | None = None
    topic_title: str = ""
    copy_text: str = ""
    hot_value: str = ""
    source: str = ""
    chars: int = 0
    created_at: str = ""


def connect_db() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=_env("DB_HOST"),
        port=int(_env("DB_PORT") or "5432"),
        dbname=_env("DB_NAME"),
        user=_env("DB_USER"),
        password=_env("DB_PASSWORD"),
        connect_timeout=10,
        cursor_factory=psycopg2.extras.DictCursor,
    )
    conn.autocommit = True
    schema = _env("DB_SCHEMA") or "wangyafei"
    with conn.cursor() as cur:
        cur.execute("SET search_path TO %s", (schema,))
    _sql_ensure_tables(conn)
    return conn


def _sql_ensure_tables(conn: psycopg2.extensions.connection) -> None:
    """Create tables if not exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                deepseek_api_key TEXT NOT NULL DEFAULT '',
                qwen_api_key TEXT NOT NULL DEFAULT '',
                global_prompt TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                content_blocks JSONB NOT NULL DEFAULT '[]'::jsonb,
                images JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                topic_title TEXT NOT NULL DEFAULT '',
                copy_text TEXT NOT NULL DEFAULT '',
                hot_value TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                chars INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def _exec_values(conn, sql: str, params: tuple, fetch: bool = False, fetch_one: bool = False) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if fetch_one:
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch:
            return [dict(r) for r in cur.fetchall()]
    return None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def load_settings(conn: psycopg2.extensions.connection) -> SettingsRow | None:
    row = _exec_values(
        conn,
        "SELECT deepseek_api_key, qwen_api_key, global_prompt, created_at::text, updated_at::text FROM settings WHERE id = 1",
        (),
        fetch_one=True,
    )
    if not row:
        return None
    return SettingsRow(
        deepseek_api_key=row.get("deepseek_api_key", ""),
        qwen_api_key=row.get("qwen_api_key", ""),
        global_prompt=row.get("global_prompt", ""),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def save_settings(
    conn: psycopg2.extensions.connection,
    *,
    deepseek_api_key: str = "",
    qwen_api_key: str = "",
    global_prompt: str = "",
) -> None:
    _exec_values(
        conn,
        """INSERT INTO settings (id, deepseek_api_key, qwen_api_key, global_prompt, updated_at)
           VALUES (1, %s, %s, %s, now())
           ON CONFLICT (id) DO UPDATE SET
               deepseek_api_key = EXCLUDED.deepseek_api_key,
               qwen_api_key      = EXCLUDED.qwen_api_key,
               global_prompt     = EXCLUDED.global_prompt,
               updated_at        = now()""",
        (deepseek_api_key, qwen_api_key, global_prompt),
    )


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def _draft_from_row(row: dict) -> DraftRow:
    return DraftRow(
        id=row.get("id"),
        title=row.get("title", ""),
        content_blocks=row.get("content_blocks", "[]") if isinstance(row.get("content_blocks"), str) else json.dumps(row.get("content_blocks", [])),
        images=row.get("images", "[]") if isinstance(row.get("images"), str) else json.dumps(row.get("images", [])),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


import json  # noqa: E402


def create_draft(
    conn: psycopg2.extensions.connection,
    *,
    title: str = "",
    content_blocks: str = "[]",
    images: str = "[]",
) -> DraftRow:
    row = _exec_values(
        conn,
        """INSERT INTO drafts (title, content_blocks, images)
           VALUES (%s, %s::jsonb, %s::jsonb)
           RETURNING id, title, content_blocks::text, images::text, created_at::text, updated_at::text""",
        (title, content_blocks, images),
        fetch_one=True,
    )
    return _draft_from_row(row)


def get_all_drafts(conn: psycopg2.extensions.connection) -> list[DraftRow]:
    rows = _exec_values(
        conn,
        "SELECT id, title, content_blocks::text, images::text, created_at::text, updated_at::text FROM drafts ORDER BY updated_at DESC",
        (),
        fetch=True,
    )
    return [_draft_from_row(r) for r in (rows or [])]


def get_draft(conn: psycopg2.extensions.connection, draft_id: int) -> DraftRow | None:
    row = _exec_values(
        conn,
        "SELECT id, title, content_blocks::text, images::text, created_at::text, updated_at::text FROM drafts WHERE id = %s",
        (draft_id,),
        fetch_one=True,
    )
    if not row:
        return None
    return _draft_from_row(row)


def update_draft(
    conn: psycopg2.extensions.connection,
    *,
    draft_id: int,
    title: str = "",
    content_blocks: str = "[]",
    images: str = "[]",
) -> DraftRow:
    row = _exec_values(
        conn,
        """UPDATE drafts SET title = %s, content_blocks = %s::jsonb, images = %s::jsonb, updated_at = now()
           WHERE id = %s
           RETURNING id, title, content_blocks::text, images::text, created_at::text, updated_at::text""",
        (title, content_blocks, images, draft_id),
        fetch_one=True,
    )
    return _draft_from_row(row)


def delete_draft(conn: psycopg2.extensions.connection, *, draft_id: int) -> None:
    _exec_values(conn, "DELETE FROM drafts WHERE id = %s", (draft_id,))


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def record_history(
    conn: psycopg2.extensions.connection,
    *,
    topic_title: str = "",
    copy_text: str = "",
    hot_value: str = "",
    source: str = "",
    chars: int = 0,
) -> HistoryRow:
    row = _exec_values(
        conn,
        """INSERT INTO history (topic_title, copy_text, hot_value, source, chars)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING id, topic_title, copy_text, hot_value, source, chars, created_at::text""",
        (topic_title, copy_text, hot_value, source, chars),
        fetch_one=True,
    )
    return HistoryRow(
        id=row.get("id"),
        topic_title=row.get("topic_title", ""),
        copy_text=row.get("copy_text", ""),
        hot_value=row.get("hot_value", ""),
        source=row.get("source", ""),
        chars=row.get("chars", 0),
        created_at=row.get("created_at", ""),
    )


def get_history(conn: psycopg2.extensions.connection, limit: int = 20) -> list[HistoryRow]:
    rows = _exec_values(
        conn,
        "SELECT id, topic_title, copy_text, hot_value, source, chars, created_at::text FROM history ORDER BY created_at DESC LIMIT %s",
        (limit,),
        fetch=True,
    )
    return [
        HistoryRow(
            id=r.get("id"),
            topic_title=r.get("topic_title", ""),
            copy_text=r.get("copy_text", ""),
            hot_value=r.get("hot_value", ""),
            source=r.get("source", ""),
            chars=r.get("chars", 0),
            created_at=r.get("created_at", ""),
        )
        for r in (rows or [])
    ]
