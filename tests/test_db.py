from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest.mock import patch

import pytest

# patch env before importing db module so DEFAULT values don't use dev env
os.environ.pop("DB_HOST", None)
os.environ.pop("DB_PASSWORD", None)

from hotstream.db import (  # noqa: E402
    DraftRow,
    SettingsRow,
    _exec_values,
    _sql_ensure_tables,
    connect_db,
    create_draft,
    delete_draft,
    get_all_drafts,
    get_draft,
    get_history,
    load_settings,
    record_history,
    save_settings,
    update_draft,
)

TEST_ENV = {
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "testdb",
    "DB_USER": "testuser",
    "DB_PASSWORD": "testpass",
    "DB_SCHEMA": "test_schema",
}


def _fake_connect():
    """Return a dict to simulate cursor behaviour."""
    return {"rows": [], "last_sql": "", "last_params": None}


# ---------------------------------------------------------------------------
# RED tests — database module
# ---------------------------------------------------------------------------


class TestConnectDb:
    def test_uses_env_vars_for_connection(self):
        """connect_db must read DB_* from env and pass correct kwargs to psycopg2."""
        with patch.dict(os.environ, TEST_ENV, clear=True), patch(
            "hotstream.db.psycopg2.connect"
        ) as mock_connect:
            mock_connect.return_value = _MagicConn()
            connect_db()
            kwargs = mock_connect.call_args.kwargs
            assert kwargs["host"] == "localhost"
            assert kwargs["port"] == 5432
            assert kwargs["dbname"] == "testdb"
            assert kwargs["user"] == "testuser"
            assert kwargs["password"] == "testpass"

    def test_sets_search_path_after_connect(self):
        """connect_db must set search_path to configured schema."""
        with patch.dict(os.environ, TEST_ENV, clear=True), patch(
            "hotstream.db.psycopg2.connect"
        ) as mock_connect:
            mock_conn = _MagicConn()
            mock_connect.return_value = mock_conn
            connect_db()
            executed = [c[0] for c in mock_conn._cursor.executed]
            assert any("SET search_path TO %s" in sql for sql in executed)
            # verify the schema name was passed as a parameter
            params_seen = [c[1] for c in mock_conn._cursor.executed if "SET search_path" in c[0]]
            assert any(p == ("test_schema",) for p in params_seen)

class TestSqlEnsureTables:
    def test_creates_settings_table_in_search_path(self):
        """_sql_ensure_tables must issue CREATE TABLE IF NOT EXISTS for settings."""
        mock_conn = _MagicConn()
        _sql_ensure_tables(mock_conn)
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("CREATE TABLE IF NOT EXISTS settings" in sql for sql in executed)

    def test_creates_drafts_table_in_search_path(self):
        """_sql_ensure_tables must issue CREATE TABLE IF NOT EXISTS for drafts."""
        mock_conn = _MagicConn()
        _sql_ensure_tables(mock_conn)
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("CREATE TABLE IF NOT EXISTS drafts" in sql for sql in executed)

    def test_creates_history_table_in_search_path(self):
        """_sql_ensure_tables must issue CREATE TABLE IF NOT EXISTS for history."""
        mock_conn = _MagicConn()
        _sql_ensure_tables(mock_conn)
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("CREATE TABLE IF NOT EXISTS history" in sql for sql in executed)


class TestLoadSettings:
    def test_returns_none_when_no_row(self):
        """load_settings returns None when table is empty."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = []
        result = load_settings(mock_conn)
        assert result is None

    def test_returns_settings_row_when_present(self):
        """load_settings returns SettingsRow with correct values."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"deepseek_api_key": "sk-deepseek", "qwen_api_key": "sk-qwen", "global_prompt": "custom global prompt", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-02T00:00:00+00:00"}
        ]
        result = load_settings(mock_conn)
        assert result is not None
        assert result.deepseek_api_key == "sk-deepseek"
        assert result.qwen_api_key == "sk-qwen"
        assert result.global_prompt == "custom global prompt"


class TestSaveSettings:
    def test_upserts_settings_row(self):
        """save_settings must UPSERT into settings table."""
        mock_conn = _MagicConn()
        save_settings(
            mock_conn,
            deepseek_api_key="sk-new",
            qwen_api_key="sk-qw",
            global_prompt="prompt",
        )
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("INSERT INTO settings" in sql and "ON CONFLICT" in sql for sql in executed)


class TestDraftCrud:
    def test_create_draft_inserts_and_returns_row(self):
        """create_draft inserts and returns a DraftRow with id."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "title": "title1", "content_blocks": '["block1"]', "images": '["img1"]', "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
        ]
        draft = create_draft(mock_conn, title="title1", content_blocks='["block1"]', images='["img1"]')
        assert draft.id == 1
        assert draft.title == "title1"

    def test_get_all_drafts_returns_list(self):
        """get_all_drafts returns list of DraftRow."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "title": "d1", "content_blocks": "[]", "images": "[]", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "title": "d2", "content_blocks": "[]", "images": "[]", "created_at": "2026-01-02T00:00:00+00:00", "updated_at": "2026-01-02T00:00:00+00:00"},
        ]
        drafts = get_all_drafts(mock_conn)
        assert len(drafts) == 2
        assert drafts[0].title == "d1"

    def test_get_draft_returns_single(self):
        """get_draft returns one DraftRow by id."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 5, "title": "mydraft", "content_blocks": "[]", "images": "[]", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
        ]
        draft = get_draft(mock_conn, draft_id=5)
        assert draft is not None
        assert draft.id == 5

    def test_get_draft_returns_none_for_missing_id(self):
        """get_draft returns None when nothing found."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = []
        assert get_draft(mock_conn, draft_id=999) is None

    def test_update_draft_updates_row(self):
        """update_draft UPDATEs draft and returns updated row."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 3, "title": "updated", "content_blocks": '["b"]', "images": '["i"]', "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-02T00:00:00+00:00"}
        ]
        draft = update_draft(mock_conn, draft_id=3, title="updated", content_blocks='["b"]', images='["i"]')
        assert draft.title == "updated"
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("UPDATE drafts SET" in sql for sql in executed)

    def test_delete_draft_removes_row(self):
        """delete_draft runs DELETE on the draft."""
        mock_conn = _MagicConn()
        delete_draft(mock_conn, draft_id=7)
        executed = [c[0] for c in mock_conn._cursor.executed]
        assert any("DELETE FROM drafts" in sql and "id = %s" in sql for sql in executed)


class TestHistory:
    def test_record_history_inserts_and_returns_row(self):
        """record_history inserts into history."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "topic_title": "t", "copy_text": "c", "hot_value": "h", "source": "s", "chars": 100, "created_at": "2026-01-01T00:00:00+00:00"}
        ]
        row = record_history(
            mock_conn,
            topic_title="t",
            copy_text="c",
            hot_value="h",
            source="s",
            chars=100,
        )
        assert row.id == 1

    def test_get_history_returns_list_ordered_by_created_at(self):
        """get_history returns list ordered by created_at."""
        mock_conn = _MagicConn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "topic_title": "t1", "copy_text": "c1", "hot_value": "h1", "source": "s1", "chars": 50, "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "topic_title": "t2", "copy_text": "c2", "hot_value": "h2", "source": "s2", "chars": 80, "created_at": "2026-01-02T00:00:00+00:00"},
        ]
        rows = get_history(mock_conn, limit=2)
        assert len(rows) == 2
        assert rows[0].topic_title == "t1"


# ---------------------------------------------------------------------------
# Fake connection helpers
# ---------------------------------------------------------------------------


class _MagicCursor:
    def __init__(self):
        self.executed: list[tuple[Any, ...]] = []
        self._fetched_rows: list[dict | tuple] = []
        self.description: list | None = None

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetched_rows:
            row = self._fetched_rows[0]
            if isinstance(row, dict):
                return row
            return _tuple_to_dict(row)
        return None

    def fetchall(self):
        return [_tuple_to_dict(r) if not isinstance(r, dict) else r for r in self._fetched_rows[:]]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _tuple_to_dict(row: tuple) -> dict:
    """Mock helper: convert tuple to dict for DictCursor compatibility."""
    if isinstance(row, dict):
        return row
    return {}


class _MagicConn:
    def __init__(self):
        self._cursor = _MagicCursor()
        self.autocommit = True

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass
