"""The AI key probe: an authenticated call, never a public catalog 200.

RED-BEFORE (the 2026-10-28 outage): the settings page proved "the key is fine"
by fetching ``{base_url}/models``. On OpenRouter that endpoint is public — it
answers 200 with 464 models for a keyring stub the provider rejects with 401
"Missing Authentication header". The page showed a healthy catalog next to a
dead key, every judge call died, and the only trace was a WARNING in
``log.txt``. Each assertion below fails on the commit before
``services/ai_key_check`` existed, because there was no probe to call.

Layers:

1. :func:`probe_key` verdicts over a fake transport (the seam is
   ``ai_key_check.HTTP_REQUEST``): a public ``/models`` 200 proves nothing, a
   ``/key`` 200 is authentication, a 404 there falls through to the 1-token
   ping, and a rejected key is named with the provider's own words.
2. The i18n of the verdict row: all five sentences exist in every locale and
   the ``{detail}`` placeholder survives translation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tabs.image_gallery.services import ai_key_check

LOCALES = ("en", "ru", "zh", "pt_BR")
STATUS_KEYS = (
    "api_key_status_ok",
    "api_key_status_missing",
    "api_key_status_rejected",
    "api_key_status_unverified",
    "api_key_status_network",
)


class _Transport:
    """A fake provider: a route table of ``path -> (status, body)``."""

    def __init__(self, routes, *, failure: str = ""):
        self.routes = dict(routes)
        self.failure = failure
        self.calls: list[tuple[str, object]] = []

    def __call__(self, url, *, api_key="", payload=None, timeout=0):
        self.calls.append((url, payload))
        assert api_key, "the probe must never call the provider unauthenticated"
        if self.failure:
            return 0, b"", self.failure
        for path, (status, body) in self.routes.items():
            if url.endswith(path):
                return status, body, ""
        return 404, b"not found", ""


def _auth_body() -> bytes:
    return json.dumps(
        {"error": {"message": "Missing Authentication header", "code": 401}}
    ).encode()


# -- probe verdicts ----------------------------------------------------------


def test_a_public_catalog_200_is_not_a_verdict_about_the_key() -> None:
    """The exact outage shape: /models answers, /key rejects the credentials."""
    transport = _Transport(
        {
            "/models": (200, b'{"data": [{"id": "z-ai/glm-5.3-flash"}]}'),
            "/key": (401, _auth_body()),
        }
    )
    ok, reason, detail = ai_key_check.probe_key(
        "https://openrouter.ai/api/v1",
        "stub-key",
        "z-ai/glm-5.3-flash",
        request=transport,
    )
    assert ok is False
    assert reason == ai_key_check.REASON_AUTH
    assert "401" in detail and "Missing Authentication header" in detail
    assert all(not url.endswith("/models") for url, _payload in transport.calls), (
        "the probe must not consult the unauthenticated catalog endpoint"
    )


def test_the_key_endpoint_200_is_authentication_without_spending_tokens() -> None:
    transport = _Transport({"/key": (200, b'{"data": {"label": "ok"}}')})
    ok, reason, detail = ai_key_check.probe_key(
        "https://openrouter.ai/api/v1", "real-key", request=transport
    )
    assert (ok, reason, detail) == (True, ai_key_check.REASON_OK, "")
    assert len(transport.calls) == 1, "a passing /key probe needs no second call"


def test_a_provider_without_key_endpoint_falls_through_to_a_one_token_ping() -> None:
    transport = _Transport({"/key": (404, b"not found"), "/chat/completions": (200, b"{}")})
    ok, reason, _detail = ai_key_check.probe_key(
        "https://api.example.test/v1",
        "real-key",
        "vendor/model",
        request=transport,
    )
    assert (ok, reason) == (True, ai_key_check.REASON_OK)
    assert [url.rsplit("/", 1)[-1] for url, _ in transport.calls] == [
        "key",
        "completions",
    ]
    payload = transport.calls[1][1]
    assert payload["model"] == "vendor/model"
    assert payload["max_tokens"] == 1, "the ping must stay a 1-token request"


def test_a_rejected_ping_names_the_provider_words() -> None:
    transport = _Transport(
        {"/key": (404, b""), "/chat/completions": (401, _auth_body())}
    )
    ok, reason, detail = ai_key_check.probe_key(
        "https://api.example.test/v1", "stub-key", "vendor/model", request=transport
    )
    assert (ok, reason) == (False, ai_key_check.REASON_AUTH)
    assert "Missing Authentication header" in detail


def test_statuses_that_mean_no_such_endpoint_are_not_key_failures() -> None:
    for status in (404, 405, 501):
        transport = _Transport(
            {"/key": (status, b""), "/chat/completions": (200, b"{}")}
        )
        ok, reason, _detail = ai_key_check.probe_key(
            "https://api.example.test/v1", "real-key", "vendor/model", request=transport
        )
        assert (ok, reason) == (True, ai_key_check.REASON_OK), status


def test_a_rate_limited_key_authenticated() -> None:
    transport = _Transport({"/key": (429, b'{"error": "rate limited"}')})
    ok, reason, detail = ai_key_check.probe_key(
        "https://openrouter.ai/api/v1", "real-key", request=transport
    )
    assert (ok, reason) == (True, ai_key_check.REASON_OK)
    assert "429" in detail


def test_no_key_and_no_endpoint_are_named_before_any_request() -> None:
    transport = _Transport({})
    assert ai_key_check.probe_key("", "k", request=transport)[1] == (
        ai_key_check.REASON_NO_BASE_URL
    )
    assert ai_key_check.probe_key("https://x.test/v1", "", request=transport)[1] == (
        ai_key_check.REASON_NO_KEY
    )
    assert transport.calls == [], "an unanswerable probe must not reach the network"


def test_a_provider_without_key_endpoint_and_without_a_model_is_unverified() -> None:
    """No model to ping is 'not checked', never a fake ok or a fake rejection."""
    transport = _Transport({"/key": (404, b"")})
    ok, reason, detail = ai_key_check.probe_key(
        "https://api.example.test/v1", "real-key", request=transport
    )
    assert (ok, reason) == (False, ai_key_check.REASON_NO_MODEL)
    assert "model" in detail
    assert len(transport.calls) == 1, "no model means no second probe"


def test_a_dead_endpoint_is_a_network_verdict_not_an_auth_verdict() -> None:
    transport = _Transport({}, failure=ai_key_check.REASON_NETWORK)
    ok, reason, _detail = ai_key_check.probe_key(
        "https://api.example.test/v1", "real-key", request=transport
    )
    assert (ok, reason) == (False, ai_key_check.REASON_NETWORK)


def test_every_reason_is_in_the_vocabulary() -> None:
    assert set(ai_key_check.REASONS) == {
        ai_key_check.REASON_OK,
        ai_key_check.REASON_NO_KEY,
        ai_key_check.REASON_NO_BASE_URL,
        ai_key_check.REASON_NO_MODEL,
        ai_key_check.REASON_AUTH,
        ai_key_check.REASON_HTTP,
        ai_key_check.REASON_NETWORK,
    }


# -- the verdict row is localized in every locale ----------------------------


def _settings(locale: str) -> dict:
    path = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "i18n"
        / locale
        / "image_gallery.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["image_gallery"]["settings"]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_key_verdict_sentences_exist_in_every_locale(locale: str) -> None:
    settings = _settings(locale)
    for key in STATUS_KEYS:
        value = settings.get(key)
        assert isinstance(value, str) and value, f"{locale}: {key} is missing"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_detail_placeholder_survives_translation(locale: str) -> None:
    settings = _settings(locale)
    for key in ("api_key_status_rejected", "api_key_status_unverified"):
        assert "{detail}" in settings[key], f"{locale}: {key} lost {{detail}}"
