"""The profile request must not starve its own answer (2026-10-26 defect).

Recorded owner log (``IMGSLI_AI_DEBUG=1``, 10 images, ``z-ai/glm-5.3-flash``):
``metric profile: select scheduled (items=10 gen=2)`` → the axis request came
back ``finish=length content_chars=0 reasoning_chars=2305``
(``completion_tokens=560``, ``reasoning_tokens=560``, cost 0.0004) → only a
DEBUG line said ``reply yielded no usable axis`` → ``profile source:
heuristic-camera (fallback)``. The mandatory reasoner spent the WHOLE
completion on its chain-of-thought: the budget was the bare
``estimate_ask_max_tokens`` value (``count=2`` → ``400 + 2*24`` ×1.25 low-effort
headroom = 560), an ANSWER estimate that the CoT ate.

Falsification story (what each test would catch):

- a budget that is still a multiplier over an answer estimate (the reasoning
  allowance would be inside the answer's number again) or that ignores the
  effort;
- an OpenRouter payload without ``reasoning.exclude`` / bounded effort while
  the per-card analyze call has it (the exact asymmetry that starved this
  request);
- a selector that gives up after ONE truncated reply instead of retrying with a
  bigger cap, or that retries in a loop;
- a retry that does not actually raise ``max_tokens`` (the same starved budget
  would produce the same empty answer);
- a quality drop that stays on the DEBUG channel (invisible without
  the IMGSLI_AI_DEBUG gate), or a WARN that omits finish_reason/budget/model;
- a truncated/failed reply being written to the profile pin (a poisoned entry
  would serve "no axes" for the whole folder generation).

Network-free: the transport is injected and image encoding is stubbed.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.services import profile_cache
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.use_cases import profile_select
from tabs.image_gallery.use_cases.profile_ai import (
    build_profile_request,
    choose_profile_sync,
)
from tabs.image_gallery.use_cases.profile_ai_request import (
    PROFILE_ANSWER_RESERVE,
    PROFILE_MAX_TOKENS_CAP,
    PROFILE_REASONING_ALLOWANCE,
    profile_request_budget,
    retry_profile_budget,
)
from tabs.image_gallery.use_cases.profile_probe import salience_summary

OPENROUTER = "https://openrouter.ai/api/v1"
MODEL = "z-ai/glm-5.3-flash"


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _item(name: str, mtime: int = 1, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics)
    )


def _items():
    return [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "enabled": True,
        "api_key": "k",
        "base_url": OPENROUTER,
        "model": MODEL,
        "reasoning_effort": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


#: A COMPLETE selector answer: the rule is 5..8 axes, so a 1-2 axis reply is a
#: refusal now (retried once, then WARN + fallback) — the defect this row fixes.
_THREE_AXES = ["sharpness", "noise", "exposure", "clipping", "white_balance"]


def _answer(axes) -> dict:
    return {
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps({"axes": axes})},
                "finish_reason": "stop",
            }
        ],
    }


def _starved(reasoning_chars: int = 2305) -> dict:
    """The recorded reply: no content, a long CoT, cut off at the cap."""
    return {
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "x" * reasoning_chars,
                },
                "finish_reason": "length",
            }
        ],
        "usage": {
            "completion_tokens": 560,
            "completion_tokens_details": {"reasoning_tokens": 560},
        },
    }


def _key(items) -> str:
    return profile_cache.profile_cache_key(
        items,
        mode="camera",
        model=MODEL,
        base_url=OPENROUTER,
        reasoning_effort="auto",
    )


# --------------------------------------------------------------------------
# budget arithmetic — answer reserve ON TOP of a reasoning allowance
# --------------------------------------------------------------------------


def test_budget_reserves_the_answer_on_top_of_the_reasoning_allowance():
    from tabs.image_gallery.services.ask_router import estimate_ask_max_tokens

    starved = estimate_ask_max_tokens({"count": 2}, effort="auto")
    assert starved == 560, "the recorded starved budget was 560 (count=2, low)"

    budget = profile_request_budget(2, "low")
    assert budget >= PROFILE_ANSWER_RESERVE + PROFILE_REASONING_ALLOWANCE["low"]
    assert budget > starved, (
        "the budget must be bigger than the answer estimate the CoT ate: "
        "answer reserve + reasoning allowance, not a multiplier over one number"
    )


def test_budget_scales_with_the_effort_allowance_and_stays_capped():
    low = profile_request_budget(2, "low")
    medium = profile_request_budget(2, "medium")
    high = profile_request_budget(2, "high")
    assert low < medium < high
    assert high <= PROFILE_MAX_TOKENS_CAP
    assert profile_request_budget(100, "high") <= PROFILE_MAX_TOKENS_CAP


def test_request_carries_the_reserved_budget_and_the_retry_raises_it():
    probes = _items()
    payload = build_profile_request(probes, model=MODEL, salience={}, effort="low")
    assert payload["max_tokens"] == profile_request_budget(len(probes), "low")

    retry = retry_profile_budget(payload["max_tokens"])
    assert retry > payload["max_tokens"], "a retry at the same cap cannot answer"
    assert retry <= PROFILE_MAX_TOKENS_CAP
    # The retry of an already-large budget is still capped, never unbounded.
    assert retry_profile_budget(PROFILE_MAX_TOKENS_CAP) == PROFILE_MAX_TOKENS_CAP


# --------------------------------------------------------------------------
# OpenRouter hardening — the asymmetry that starved the request
# --------------------------------------------------------------------------


def test_openrouter_request_excludes_reasoning_and_routes_a_healthy_provider():
    payload = build_profile_request(
        _items(), model=MODEL, salience={}, effort="auto", base_url=OPENROUTER
    )
    assert payload["reasoning"] == {"effort": "low", "exclude": True}, (
        "a mandatory reasoner must be capped AND told to keep its CoT out of "
        "content (the reply is parsed as JSON)"
    )
    assert payload["provider"]["require_parameters"] is True
    assert payload["provider"]["sort"] == "throughput"
    assert "models" not in payload, (
        "no silent model fallback: the profile pin names ONE model"
    )


def test_non_openrouter_request_stays_byte_identical():
    payload = build_profile_request(
        _items(), model="m", salience={}, base_url="http://plain.local/v1"
    )
    assert "reasoning" not in payload and "provider" not in payload
    assert payload["response_format"] == {"type": "json_object"}


# --------------------------------------------------------------------------
# retry once on finish=length
# --------------------------------------------------------------------------


def test_truncated_reply_is_retried_once_and_the_answer_is_pinned(tmp_path):
    cache = ProfileCache(tmp_path)
    items = _items()
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return _starved()
        return _answer(_THREE_AXES)

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )

    assert len(payloads) == 2, "finish=length must be retried exactly once"
    assert payloads[1]["max_tokens"] > payloads[0]["max_tokens"], (
        "the retry has to ask for more room — the same cap reproduces the "
        "empty reasoning-only answer"
    )
    assert payloads[1]["model"] == payloads[0]["model"]
    assert profile is not None and profile.source == "vlm"
    assert "sharpness" in profile
    assert cache.get(_key(items)) == profile, "the answered retry is pinned"


def test_a_retry_that_still_starves_logs_a_warning_and_pins_nothing(tmp_path, caplog):
    """Owner rule 2026-10-26: a reply that never became an answer is an ERROR.

    Red-before: the series offer was pinned here, so the folder was ranked on
    camera/registry axes after a paid failure.
    """
    cache = ProfileCache(tmp_path)
    items = _items()
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return _starved()

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            items, mode="camera", settings=_settings(), cache=cache, client_call=_client
        )

    assert len(payloads) == 2, "exactly ONE retry — not a retry loop"
    assert profile is None, "no profile, and certainly not the local offer"
    assert cache.get(_key(items)) is None, "a failure is not pinned as an answer"

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "the quality drop must be visible without IMGSLI_AI_DEBUG"
    text = "\n".join(r.getMessage() for r in warnings)
    assert "finish_reason=length" in text
    assert f"max_tokens={payloads[-1]['max_tokens']}" in text
    assert f"model={MODEL}" in text
    assert "attempts=2" in text


def test_a_normal_reply_is_one_call_and_is_pinned(tmp_path):
    cache = ProfileCache(tmp_path)
    items = _items()
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return _answer(_THREE_AXES)

    first = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert len(payloads) == 1, "a complete answer must not be retried"
    assert first.source == "vlm" and "sharpness" in first

    second = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert len(payloads) == 1, "the answered generation is served from the pin"
    assert second == first


def test_a_non_length_failure_is_not_retried_but_still_warns(tmp_path, caplog):
    cache = ProfileCache(tmp_path)
    items = _items()
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return {
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "not json at all"},
                    "finish_reason": "stop",
                }
            ],
        }

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            items, mode="camera", settings=_settings(), cache=cache, client_call=_client
        )

    assert len(payloads) == 1, "only a token-cap truncation is worth a retry"
    assert profile is None, "a junk reply is an error, not the local offer"
    assert any(
        "finish_reason=stop" in r.getMessage() and f"model={MODEL}" in r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING
    ), "a junk reply is still a visible quality drop"
    assert cache.get(_key(items)) is None, "a failure must not be pinned"


def test_the_pin_key_is_unchanged_by_the_budget_fix(tmp_path):
    """The retry must not fork the cache identity (a poisoned second entry)."""
    cache = ProfileCache(tmp_path)
    items = _items()

    def _client(base_url, api_key, payload):
        return _answer(_THREE_AXES)

    choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    expected = profile_cache.profile_cache_key(
        items,
        mode="camera",
        model=MODEL,
        base_url=OPENROUTER,
        reasoning_effort="auto",
    )
    assert cache.get(expected) is not None
    assert cache.get("") is None
