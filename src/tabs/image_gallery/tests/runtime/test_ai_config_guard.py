"""An incomplete AI config never reaches the wire (one gate, three callers).

Live defect (2026-10-27 08:05): ``enabled=true`` with an empty ``model`` sent
``{"model": ""}`` to OpenRouter, which answered ``HTTP 400 "No models
provided"``; the profile selector logged a transport failure and the AI domain
finished the run with no axes, no rank and no analysis. The same config was read
as "not configured" by the tie-break, so the app held two answers to one
question:

- ``profile_ai.ai_selector_available`` — ``enabled and api_key and (model or
  base_url)``: an endpoint stood in for a model id, so a blank model passed;
- ``tie_break`` — ``enabled and api_key and model``: the blank model was refused.

Now ``services/ai_settings_store.missing_config_fields`` is the only definition
(``AiSettings.is_configured()`` / ``configured_reason()`` on top of it) and the
selector, the tie-break and Analyze all read it.

Falsification story (what each test catches):

- a settings gate that accepts a blank ``model`` (or ``base_url`` / ``api_key``)
  or an unenabled config as callable;
- a selector that spends a call on that config;
- a request builder that assembles ``{"model": ""}`` instead of refusing;
- a second copy of the condition reappearing in one of the three callers (the
  parity test drives the SAME configs through all three).

Network-free: the transport is always injected (``client_call``); no real AI
call is ever made.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.services.ai_config_gate import (
    incomplete_config_message,
    missing_config_fields,
)
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.use_cases import ai_analyze
from tabs.image_gallery.use_cases.profile_ai import (
    ai_selector_available,
    build_profile_request,
    choose_profile_sync,
)

_OPENROUTER = "https://openrouter.ai/api/v1"
_KEY = "sk-or-secret-value"


def _full(**overrides) -> AiSettings:
    base = {
        "enabled": True,
        "base_url": _OPENROUTER,
        "api_key": _KEY,
        "model": "z-ai/glm-5.3-flash",
    }
    base.update(overrides)
    return AiSettings(**base)


def _settings(**overrides) -> SimpleNamespace:
    """A duck-typed row, as the wiring lane hands it to the use_cases."""
    base = {
        "enabled": True,
        "base_url": _OPENROUTER,
        "api_key": _KEY,
        "model": "z-ai/glm-5.3-flash",
        "reasoning_effort": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _item(name: str, mtime: int = 1, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics)
    )


def _evidence_items():
    """Two members whose sharpness spread is the evidence a call needs."""
    return [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


# --------------------------------------------------------------------------
# the one gate, on AiSettings
# --------------------------------------------------------------------------


def test_a_blank_model_is_not_configured_and_the_reason_names_it():
    """The live defect: ``enabled`` + endpoint + key, model blank."""
    settings = _full(model="")

    assert settings.is_configured() is False
    assert settings.configured_reason() == "AI is not configured — missing: model"


def test_every_required_field_is_named_when_empty():
    assert _full(enabled=False).configured_reason().endswith("enabled")
    assert _full(base_url="").configured_reason().endswith("base_url")
    assert _full(api_key="").configured_reason().endswith("api_key")
    # Whitespace is empty, not a value.
    assert _full(model="   ").is_configured() is False
    assert _full(model="   ").missing_config_fields() == ("model",)


def test_the_reason_never_carries_the_key_value():
    reason = _full(api_key="").configured_reason()

    assert "api_key" in reason
    assert _KEY not in reason
    assert incomplete_config_message(()) == ""


def test_a_complete_config_is_configured():
    settings = _full()

    assert settings.is_configured() is True
    assert settings.configured_reason() == ""
    assert settings.missing_config_fields() == ()


def test_the_gate_never_raises_on_a_foreign_settings_object():
    """A settings double or a broken store reads as "not configured"."""
    assert missing_config_fields(None) == (
        "enabled",
        "base_url",
        "api_key",
        "model",
    )
    assert missing_config_fields(object()) == (
        "enabled",
        "base_url",
        "api_key",
        "model",
    )
    assert ai_selector_available(object()) is False
    assert ai_selector_available(None) is False


# --------------------------------------------------------------------------
# one definition, three callers (drift is the defect)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"model": ""},
        {"base_url": ""},
        {"api_key": ""},
        {"enabled": False},
        {"model": "", "base_url": ""},
    ],
)
def test_selector_tie_break_and_analyze_agree_on_every_config(overrides):
    """Duplicated conditions drifted once (an endpoint stood in for a model).

    All three callers must answer the same question the same way, so the
    selector can never spend a call on a config the tie-break calls unusable.
    """
    settings = _settings(**overrides)
    expected = _full(**overrides).is_configured()

    assert ai_selector_available(settings) is expected
    assert ai_analyze._is_configured(settings) is expected


# --------------------------------------------------------------------------
# the selector refuses without a request
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, named",
    [
        ({"model": ""}, "model"),
        ({"base_url": ""}, "base_url"),
        ({"api_key": ""}, "api_key"),
    ],
)
def test_an_incomplete_config_spends_no_call_and_says_what_is_missing(
    tmp_path, caplog, overrides, named
):
    """Red-before: one POST with ``{"model": ""}`` and HTTP 400 from OpenRouter."""
    calls: list = []

    def _client(base_url, api_key, payload):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"axes": ["sharpness"]}'}}]}

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            _evidence_items(),
            mode="camera",
            settings=_settings(**overrides),
            cache=ProfileCache(tmp_path),
            client_call=_client,
        )

    assert profile is None, "an unusable config must not resolve a profile"
    assert calls == [], "no HTTP call may be made for an incomplete config"

    warnings = [
        rec.getMessage()
        for rec in caplog.records
        if rec.levelno >= logging.WARNING and "profile select" in rec.getMessage()
    ]
    assert len(warnings) == 1, f"expected ONE warning line, got {warnings}"
    assert named in warnings[0], warnings[0]
    assert "Settings" in warnings[0], "the line must say what to do"
    assert _KEY not in warnings[0], "the key must never reach the log"
    assert not any(rec.exc_info for rec in caplog.records), "no traceback: no call ran"


def test_a_complete_config_still_spends_exactly_one_call(tmp_path):
    """Nothing about a COMPLETE config changes (same payload, same one call)."""
    calls: list = []

    def _client(base_url, api_key, payload):
        calls.append((base_url, api_key, payload))
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"axes": ["sharpness", "noise", "exposure", '
                            '"clipping", "white_balance"]}'
                        )
                    }
                }
            ]
        }

    profile = choose_profile_sync(
        _evidence_items(),
        mode="camera",
        settings=_settings(),
        cache=ProfileCache(tmp_path),
        client_call=_client,
    )

    assert len(calls) == 1
    base_url, api_key, payload = calls[0]
    assert base_url == _OPENROUTER and api_key == _KEY
    assert payload["model"] == "z-ai/glm-5.3-flash"
    assert profile is not None and profile.source == "vlm"


# --------------------------------------------------------------------------
# the request builder refuses an empty model instead of shipping it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["", "   ", None])
def test_build_profile_request_refuses_an_empty_model(model):
    """Red-before: the payload carried ``{"model": ""}`` to the provider."""
    with pytest.raises(ValueError) as excinfo:
        build_profile_request([_item("a.png")], model=model, salience={})

    message = str(excinfo.value)
    assert "model" in message
    assert "No models provided" in message, "the message names the live failure"
    assert "Settings" in message, "the message says what to do"


def test_build_profile_request_sends_the_model_it_was_given():
    """The refusal must not become a silent default substitution."""
    payload = build_profile_request(
        [_item("a.png")], model="custom/model", salience={}, effort="low"
    )

    assert payload["model"] == "custom/model"
