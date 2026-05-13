from unittest.mock import MagicMock, patch
from urllib.error import URLError

from hotstream.server import build_proxy_image_response


class FakeImageResponse:
    def __init__(self, body=b"image-bytes", content_type="image/png"):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def test_build_proxy_image_response_fetches_remote_image_bytes():
    with patch("hotstream.server.urllib.request.urlopen", return_value=FakeImageResponse()) as urlopen:
        status, headers, body = build_proxy_image_response("https://example.com/a.png")

    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert headers["Cache-Control"] == "public, max-age=86400"
    assert body == b"image-bytes"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://example.com/a.png"
    assert request.headers["User-agent"]


def test_build_proxy_image_response_rejects_non_http_urls():
    status, headers, body = build_proxy_image_response("file:///etc/passwd")

    assert status == 400
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert b"http" in body.lower()


def test_build_proxy_image_response_rejects_non_image_content():
    with patch("hotstream.server.urllib.request.urlopen", return_value=FakeImageResponse(content_type="text/html")):
        status, headers, body = build_proxy_image_response("https://example.com/page")

    assert status == 415
    assert b"image" in body.lower()


def test_build_proxy_image_response_handles_network_error():
    with patch("hotstream.server.urllib.request.urlopen", side_effect=URLError("down")):
        status, headers, body = build_proxy_image_response("https://example.com/a.png")

    assert status == 502
    assert b"down" in body
