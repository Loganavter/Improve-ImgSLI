from __future__ import annotations

import io
import urllib.error

import pytest

from tabs.image_gallery.services import ai_client


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.test/v1/chat/completions",
        code=code,
        msg="error",
        hdrs={},  # type: ignore[arg-type]  # empty header dict
        fp=io.BytesIO(b"{}"),
    )


def test_call_sync_raises_auth_error_on_401(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise _http_error(401)

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ai_client.AiAuthError):
        ai_client.call_sync("https://example.test/v1", "key", {})


def test_call_sync_raises_rate_limit_error_on_429(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise _http_error(429)

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ai_client.AiRateLimitError):
        ai_client.call_sync("https://example.test/v1", "key", {})


def test_call_sync_raises_network_error_on_url_error(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ai_client.AiNetworkError):
        ai_client.call_sync("https://example.test/v1", "key", {})


def test_call_sync_raises_network_error_on_other_http_status(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise _http_error(500)

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ai_client.AiNetworkError):
        ai_client.call_sync("https://example.test/v1", "key", {})