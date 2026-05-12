import json
from unittest.mock import patch

from hotstream.server import build_hot_topics_response


def test_build_hot_topics_response_returns_json_payload():
    with patch("hotstream.server.fetch_hot_topics", return_value=[
        {"rank": 1, "title": "A", "url": "https://example.com/a", "hot_value": 10, "label": "", "source": "知乎"}
    ]) as fetch:
        status, headers, body = build_hot_topics_response(source="zhihu")

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is True
    assert payload["source"] == "知乎"
    assert payload["source_key"] == "zhihu"
    assert payload["topics"][0]["title"] == "A"
    assert "updated_at" in payload
    fetch.assert_called_once_with("zhihu", limit=20)


def test_build_hot_topics_response_handles_fetch_error():
    with patch("hotstream.server.fetch_hot_topics", side_effect=RuntimeError("network down")):
        status, headers, body = build_hot_topics_response(source="xiaohongshu")

    assert status == 502
    payload = json.loads(body.decode("utf-8"))
    assert payload["success"] is False
    assert payload["source"] == "小红书"
    assert "network down" in payload["error"]
