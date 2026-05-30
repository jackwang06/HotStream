from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

# suppress real env so tests don't accidentally use real DB
os.environ.pop("DB_HOST", None)
os.environ.pop("DB_PASSWORD", None)

from hotstream.server import (  # noqa: E402
    build_drafts_crud_response,
    build_history_response,
    build_settings_get_response,
    build_settings_save_response,
)


# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------


class TestSettingsApi:
    def test_get_returns_empty_when_no_settings(self):
        """GET /api/settings returns empty defaults when DB empty."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = []

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_settings_get_response()

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["success"] is True
        assert payload["deepseek_api_key"] == ""
        assert payload["qwen_api_key"] == ""
        assert payload["global_prompt"] != ""  # should fall back to default prompt

    def test_get_returns_saved_settings(self):
        """GET /api/settings returns previously saved settings."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"deepseek_api_key": "sk-ds", "qwen_api_key": "sk-qw", "global_prompt": "my prompt", "created_at": "", "updated_at": ""}
        ]

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_settings_get_response()

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["deepseek_api_key"] == "sk-ds"
        assert payload["qwen_api_key"] == "sk-qw"
        assert payload["global_prompt"] == "my prompt"

    def test_save_updates_and_returns_settings(self):
        """POST /api/settings saves and returns settings."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"deepseek_api_key": "sk-new", "qwen_api_key": "sk-qwen", "global_prompt": "new prompt", "created_at": "", "updated_at": ""},
        ]
        raw_body = json.dumps({
            "deepseek_api_key": "sk-new",
            "qwen_api_key": "sk-qwen",
            "global_prompt": "new prompt",
        }).encode("utf-8")

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_settings_save_response(raw_body)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["success"] is True
        assert payload["deepseek_api_key"] == "sk-new"


# ---------------------------------------------------------------------------
# Drafts API
# ---------------------------------------------------------------------------


class TestDraftsApi:
    def test_list_drafts(self):
        """GET /api/drafts returns list of drafts."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "title": "d1", "content_blocks": '["t1"]', "images": '[]', "created_at": "", "updated_at": ""}
        ]

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_drafts_crud_response("GET", raw_body=b"")

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert len(payload["drafts"]) == 1
        assert payload["drafts"][0]["title"] == "d1"

    def test_create_draft(self):
        """POST /api/drafts creates a new draft."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 5, "title": "new draft", "content_blocks": '[]', "images": '[]', "created_at": "", "updated_at": ""}
        ]
        raw_body = json.dumps({"title": "new draft", "content_blocks": "[]", "images": "[]"}).encode("utf-8")

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_drafts_crud_response("POST", raw_body=raw_body)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["draft"]["id"] == 5

    def test_update_draft(self):
        """PUT /api/drafts/<id> updates a draft."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 3, "title": "updated", "content_blocks": '["b"]', "images": '[]', "created_at": "", "updated_at": ""}
        ]
        raw_body = json.dumps({"title": "updated"}).encode("utf-8")

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_drafts_crud_response("PUT", raw_body=raw_body, draft_id=3)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["draft"]["title"] == "updated"

    def test_delete_draft(self):
        """DELETE /api/drafts/<id> removes a draft."""
        mock_conn = _magic_conn()

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_drafts_crud_response("DELETE", raw_body=b"", draft_id=7)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["success"] is True

    def test_get_single_draft(self):
        """GET /api/drafts/<id> returns single draft."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 2, "title": "single", "content_blocks": "[]", "images": "[]", "created_at": "", "updated_at": ""}
        ]

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_drafts_crud_response("GET", raw_body=b"", draft_id=2)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["draft"]["id"] == 2


# ---------------------------------------------------------------------------
# History API
# ---------------------------------------------------------------------------


class TestHistoryApi:
    def test_list_history(self):
        """GET /api/history returns list of history records."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 1, "topic_title": "t1", "copy_text": "c1", "hot_value": "100", "source": "B站", "chars": 50, "created_at": ""}
        ]

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_history_response("GET", raw_body=b"")

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert len(payload["history"]) == 1

    def test_record_history(self):
        """POST /api/history records a new entry."""
        mock_conn = _magic_conn()
        mock_conn._cursor._fetched_rows = [
            {"id": 10, "topic_title": "test", "copy_text": "copy", "hot_value": "50", "source": "今日头条", "chars": 200, "created_at": ""}
        ]
        raw_body = json.dumps({
            "topic_title": "test",
            "copy_text": "copy",
            "hot_value": "50",
            "source": "今日头条",
            "chars": 200,
        }).encode("utf-8")

        with patch("hotstream.server.connect_db", return_value=mock_conn):
            status, headers, body = build_history_response("POST", raw_body=raw_body)

        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        assert payload["success"] is True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _MagicCursor:
    def __init__(self):
        self.executed = []
        self._fetched_rows: list[dict] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetched_rows:
            return self._fetched_rows.pop(0)
        return None

    def fetchall(self):
        return self._fetched_rows[:]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _magic_conn():
    conn = _MagicConn()
    return conn


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
