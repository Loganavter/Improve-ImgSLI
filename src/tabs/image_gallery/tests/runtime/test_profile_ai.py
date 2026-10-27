"""P2/P3 — the VLM profile selector and its disk pin.

Falsification story (what each test would catch):

- a request that does not supply one image per probe member, does not force
  ``response_format={"type": "json_object"}``, or omits pool ids/labels from the
  text (the model could answer in prose / invent axes);
- a parser that fabricates axes from free-form ids, accepts an array of unknown
  ids, or crashes on junk instead of returning ``None``;
- a selector that calls the transport when AI is off, calls it twice for
  unchanged inputs (the pin must serve the second run), pins a malformed reply,
  or leaks a transport exception into the caller;
- a cache key that ignores the mtime / membership / mode / model (a stale
  selection would be served across a folder change), or that serves a record
  written under a different cache version.

Network-free: the transport is always injected (``client_call``) and image
encoding is stubbed; no real AI call is ever made.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.services import profile_cache
from tabs.image_gallery.services.metric_profile import MEASURED_POOL, MetricProfile
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.use_cases import profile_ai, profile_select
from tabs.image_gallery.use_cases.profile_ai import (
    ai_selector_available,
    build_profile_request,
    choose_profile_sync,
    parse_profile_reply,
    profile_fingerprint,
)
from tabs.image_gallery.use_cases.profile_probe import salience_summary


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _item(name: str, mtime: int = 1, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics)
    )


def _evidence_items():
    """Two members whose sharpness spread IS the evidence a call needs.

    Owner design 2026-10-26: no measured difference ⇒ no request (the selector is
    skipped with a WARN), so every test that expects a call must carry evidence.
    """
    return [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]


#: A complete answer: 5 axes (the rule is 5..8), all evidence-backed registry ids.
_COMPLETE_AXES = {"axes": ["sharpness", "noise", "exposure", "clipping", "white_balance"]}


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "enabled": True,
        "api_key": "k",
        "base_url": "http://x",
        "model": "m",
        "reasoning_effort": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _chat(answer) -> dict:
    """A chat envelope whose assistant message is *answer* (dict or str)."""
    content = answer if isinstance(answer, str) else json.dumps(answer)
    return {"choices": [{"message": {"content": content}}]}


# --------------------------------------------------------------------------
# availability gate
# --------------------------------------------------------------------------


def test_ai_selector_available_requires_enabled_key_and_endpoint():
    assert ai_selector_available(_settings()) is True
    # An endpoint is NOT a model id: this config sent ``{"model": ""}`` and the
    # provider answered HTTP 400 "No models provided" (measured 2026-10-27).
    assert ai_selector_available(_settings(model="", base_url="http://x")) is False
    assert ai_selector_available(_settings(enabled=False)) is False
    assert ai_selector_available(_settings(api_key="")) is False
    assert ai_selector_available(_settings(base_url="")) is False
    assert ai_selector_available(_settings(model="", base_url="")) is False


def test_ai_selector_available_never_raises():
    assert ai_selector_available(None) is False
    assert ai_selector_available(object()) is False


# --------------------------------------------------------------------------
# fingerprint / cache key
# --------------------------------------------------------------------------


def test_fingerprint_is_order_independent():
    a, b = _item("a.png"), _item("b.png")
    first = profile_fingerprint([a, b], mode="camera", model="m")
    assert first == profile_fingerprint([b, a], mode="camera", model="m")


def test_fingerprint_changes_with_every_identity_component():
    a, b = _item("a.png"), _item("b.png")
    key = profile_fingerprint([a, b], mode="camera", model="m")

    assert profile_fingerprint([_item("a.png", mtime=2), b], mode="camera", model="m") != key
    assert profile_fingerprint([a, b, _item("c.png")], mode="camera", model="m") != key
    assert profile_fingerprint([a, b], mode="fidelity", model="m") != key
    assert profile_fingerprint([a, b], mode="camera", model="other") != key
    assert profile_fingerprint([a, b], mode="camera", model="m", pool=("sharpness",)) != key
    # The endpoint and the reasoning effort change the ANSWER, so they are part
    # of the pin identity — the same model id on two providers is not one pin.
    assert (
        profile_fingerprint([a, b], mode="camera", model="m", base_url="http://x")
        != key
    )
    assert (
        profile_fingerprint(
            [a, b], mode="camera", model="m", reasoning_effort="high"
        )
        != key
    )


def test_fingerprint_normalises_the_endpoint():
    """Two spellings of one URL pin the same selection (no pointless re-roll)."""
    a, b = _item("a.png"), _item("b.png")
    left = profile_fingerprint([a, b], mode="camera", model="m", base_url="HTTP://X.test/v1/")
    right = profile_fingerprint([a, b], mode="camera", model="m", base_url="http://x.test/v1")
    assert left == right


def test_profile_pin_is_scoped_to_the_provider_endpoint(tmp_path):
    """Same model id, different base_url → the old endpoint's pin is a MISS.

    The fixed bug (queue id ``task-ai-cache-identity-truth-2026-10-20``): the
    pin key covered members+mode+model+pool only, so pointing the same model id
    at a new endpoint silently reused the previous endpoint's VLM selection.
    Old pins (written before the endpoint was part of the key) stay on disk as
    unreachable orphans — no silent migration, a cache reset deletes them.
    """
    cache = ProfileCache(tmp_path)
    items = _evidence_items()
    pinned = MetricProfile(axis_ids=("ssim",), mode="camera", source="vlm")
    cache.put(
        profile_cache.profile_cache_key(
            items,
            mode="camera",
            model="m",
            base_url="http://x",
            reasoning_effort="auto",
        ),
        pinned,
    )
    calls: list = []

    def _client(base_url, api_key, payload):
        calls.append(base_url)
        return _chat(_COMPLETE_AXES)

    # Same model id on another endpoint: the A pin must not be served.
    profile = choose_profile_sync(
        items,
        mode="camera",
        settings=_settings(base_url="http://y"),
        cache=cache,
        client_call=_client,
    )
    assert calls == ["http://y"], "a foreign endpoint's pin short-circuited the call"
    assert profile.axis_ids == (
        "sharpness",
        "exposure",
        "clipping",
        "noise",
        "white_balance",
    )

    # Endpoint A still hits its own pin.
    calls.clear()
    same = choose_profile_sync(
        items,
        mode="camera",
        settings=_settings(base_url="http://x"),
        cache=cache,
        client_call=_client,
    )
    assert calls == [], "the same endpoint must still be served from its pin"
    assert same == pinned


# --------------------------------------------------------------------------
# request shape
# --------------------------------------------------------------------------


def test_build_profile_request_leads_with_evidence_and_names_no_axis_of_its_own():
    """The probe request: EVIDENCE + the shape rule + one image each.

    Owner design 2026-10-26: the examples list is gone. The prompt carries the
    measured evidence (per-axis spread, per-probe scores) and the schema, and it
    never names an axis of its own — a labelled menu is what the model anchored
    on, turning a paid answer into a guess.
    """
    probes = [
        _item("a.png", sharpness=0.0, noise=0.3),
        _item("b.png", sharpness=400.0, noise=0.3),
        _item("c.png", sharpness=200.0, noise=0.3),
    ]
    summary = salience_summary(probes, probes=probes)
    payload = build_profile_request(probes, model="m", salience=summary)

    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "m"
    assert [m["role"] for m in payload["messages"]] == ["user"]
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "text"
    text = content[0]["text"]
    assert "ONLY from this list" not in text
    assert "EXAMPLES of what an axis can be" not in text, "the examples menu is gone"
    assert "EVIDENCE" in text and "from the evidence" in text, (
        "the evidence leads and is what the axes must be tied to"
    )
    assert "members" in text and "spread" in text, (
        "the measured spreads of THIS series travel with the images"
    )
    assert "why" in text, "every axis must be tied to an observed difference"
    assert "from 5 to 8" in text.lower()
    assert "ONLY a JSON object" in text
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert len(image_parts) == 3
    assert all(part["image_url"]["url"].startswith("data:image/png;base64,") for part in image_parts)
    assert payload["max_tokens"] > 0


def test_build_profile_request_positive_max_tokens_wins():
    payload = build_profile_request([_item("a.png")], model="m", salience={}, max_tokens=7)
    assert payload["max_tokens"] == 7


def test_build_profile_request_skips_unreadable_images(monkeypatch):
    from tabs.image_gallery.services import vlm

    def _boom(path):
        raise OSError("gone")

    monkeypatch.setattr(vlm, "_encode_image", _boom)
    payload = build_profile_request([_item("a.png")], model="m", salience={})
    parts = payload["messages"][0]["content"]
    assert not any(part["type"] == "image_url" for part in parts)


# --------------------------------------------------------------------------
# tolerant parse
# --------------------------------------------------------------------------


def test_parse_profile_reply_accepts_the_axes_object():
    profile = parse_profile_reply('{"axes": ["noise", "sharpness"]}', mode="camera")
    assert profile is not None
    assert profile.axis_ids == tuple(a for a in MEASURED_POOL if a in {"sharpness", "noise"})
    assert profile.source == "vlm" and profile.mode == "camera"


def test_parse_profile_reply_accepts_a_bare_array_and_fences():
    assert parse_profile_reply('["sharpness"]') is not None
    assert parse_profile_reply('```json\n{"axes": ["sharpness"]}\n```') is not None


def test_parse_profile_reply_keeps_free_names_and_drops_a_repeat():
    """``invented`` is now the judge's own entry; the repeat still loses."""
    profile = parse_profile_reply('{"axes": ["invented", "sharpness", "sharpness"]}')
    assert profile is not None and profile.axis_ids == ("sharpness",)
    assert [entry.name for entry in profile.axis_entries] == ["invented"]


def test_parse_profile_reply_returns_none_on_junk():
    # NOTE: a bare name outside the pool is NO LONGER junk (owner rule 2026-10-27:
    # it is kept with ``definition=""``); an unusable name still is.
    for junk in ("", "hello world", "42", '{"axes": []}', '{"axes": ["   "]}', None):
        assert parse_profile_reply(junk) is None


# --------------------------------------------------------------------------
# choose_profile_sync — the single entry
# --------------------------------------------------------------------------


def test_choose_profile_sync_ai_unavailable_is_none_without_a_call(tmp_path):
    """Owner rule 2026-10-26: a selected AI backend that cannot answer is an ERROR.

    Red-before: the series offer was returned and pinned, so the run continued on
    camera/registry axes ("снова все метрики из camera режима").
    """
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat({"axes": ["sharpness"]})

    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    profile = choose_profile_sync(
        items,
        mode="camera",
        settings=_settings(enabled=False),
        cache=ProfileCache(tmp_path),
        client_call=_client,
    )
    assert calls == []
    assert profile is None, "no local axis set may stand in for the AI answer"


def test_choose_profile_sync_pin_hit_skips_the_call(tmp_path):
    cache = ProfileCache(tmp_path)
    items = _evidence_items()
    pinned = MetricProfile(axis_ids=("ssim",), mode="camera", source="vlm")
    cache.put(
        profile_cache.profile_cache_key(
            items, mode="camera", model="m", base_url="http://x", reasoning_effort="auto"
        ),
        pinned,
    )

    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat({"axes": ["sharpness"]})

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert calls == []
    assert profile == pinned and profile.source == "vlm"


def test_choose_profile_sync_calls_once_then_pins(tmp_path):
    cache = ProfileCache(tmp_path)
    items = _evidence_items()
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat(_COMPLETE_AXES)

    first = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    second = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert len(calls) == 1
    assert first == second
    assert first.source == "vlm" and first.mode == "camera"
    assert "sharpness" in first and "noise" in first


def test_choose_profile_sync_malformed_reply_returns_none_and_pins_nothing(tmp_path):
    """A junk reply is an ERROR (owner 2026-10-26), and it pins NOTHING.

    The old contract pinned the series offer here. That made a paid failure look
    like a resolved profile and let the folder be ranked on local axes; it is the
    silent fallback the owner forbade.
    """
    cache = ProfileCache(tmp_path)
    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat("not json at all")

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert profile is None, "a junk reply produces no profile at all"
    key = profile_cache.profile_cache_key(
        items, mode="camera", model="m", base_url="http://x", reasoning_effort="auto"
    )
    assert cache.get(key) is None, "a failure must not be pinned as an answer"

    second = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert second is None
    assert len(calls) == 2, (
        "a FAILURE is not pinned (that would turn a transient error into a "
        "permanent one); the stage gate — not the pin — keeps one attempt per "
        "folder generation, so each explicit re-resolve pays its own call"
    )


def test_choose_profile_sync_drops_ids_outside_the_pool(tmp_path):
    cache = ProfileCache(tmp_path)
    items = [_item("a.png"), _item("b.png")]

    def _client(*args, **kwargs):
        return _chat({"axes": ["invented_axis"]})

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert profile is None, "an axis the profile cannot score is not a profile"
    assert (
        cache.get(
            profile_cache.profile_cache_key(
                items,
                mode="camera",
                model="m",
                base_url="http://x",
                reasoning_effort="auto",
            )
        )
        is None
    ), "the unusable pick must not leak into the pin — and neither may a fallback"


def test_choose_profile_sync_transport_raise_is_an_error_not_a_fallback(tmp_path):
    items = [_item("a.png"), _item("b.png")]

    def _boom(*args, **kwargs):
        raise RuntimeError("network exploded")

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=ProfileCache(tmp_path), client_call=_boom
    )
    assert profile is None, "a network failure is an error, not the camera axes"


def test_choose_profile_sync_no_items_is_none_without_a_call(tmp_path):
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat({"axes": ["sharpness"]})

    profile = choose_profile_sync(
        [], mode="camera", settings=_settings(), cache=ProfileCache(tmp_path), client_call=_client
    )
    assert calls == []
    assert profile is None, "no members ⇒ no evidence ⇒ an error, not an offer"


def test_choose_profile_sync_default_transport_is_ai_client_call_sync(monkeypatch, tmp_path):
    from tabs.image_gallery.services import ai_client

    captured: dict = {}

    def _fake_call_sync(base_url, api_key, payload):
        captured.update(base_url=base_url, api_key=api_key, payload=payload)
        return _chat(_COMPLETE_AXES)

    monkeypatch.setattr(ai_client, "call_sync", _fake_call_sync)
    items = _evidence_items()
    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=ProfileCache(tmp_path)
    )
    assert captured["base_url"] == "http://x"
    assert captured["api_key"] == "k"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert profile.source == "vlm"


# --------------------------------------------------------------------------
# disk pin — roundtrip, identity, version gate
# --------------------------------------------------------------------------


def test_profile_cache_roundtrip(tmp_path):
    cache = ProfileCache(tmp_path)
    profile = MetricProfile(
        axis_ids=("noise", "sharpness"), mode="fidelity", source="vlm", salient_axes=("noise",)
    )
    cache.put("key1", profile)
    assert cache.get("key1") == profile
    assert cache.get("missing") is None


def test_profile_cache_version_mismatch_is_a_miss(tmp_path):
    cache = ProfileCache(tmp_path)
    profile = MetricProfile(axis_ids=("sharpness",), mode="camera", source="vlm")
    cache.put("key1", profile)
    stored = json.loads((tmp_path / "profile_key1.json").read_text(encoding="utf-8"))
    stored["version"] = profile_cache.PROFILE_CACHE_VERSION + 1
    (tmp_path / "profile_key1.json").write_text(json.dumps(stored), encoding="utf-8")
    assert cache.get("key1") is None


def test_profile_cache_does_not_pin_an_empty_profile(tmp_path):
    cache = ProfileCache(tmp_path)
    cache.put("key1", MetricProfile())
    assert cache.get("key1") is None


def test_profile_ai_is_qt_free_at_import():
    source = Path(profile_ai.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import Qt" not in source


def test_module_exports_are_the_frozen_interface():
    assert set(profile_ai.__all__) == {
        "MAX_PROFILE_AXES",
        "MIN_PROFILE_AXES",
        "ai_selector_available",
        "axis_count_report",
        "axis_evidence_split",
        "build_profile_request",
        "choose_profile_sync",
        "describe_axis_provenance",
        "missing_evidence_rows",
        "parse_profile_reply",
        "per_series_profile",
        "per_series_profiles",
        "profile_axis_count",
        "profile_fingerprint",
    }


def test_a_locally_sourced_pin_is_not_replayed(tmp_path):
    """A stale pin holding the local axis set must not silence the model.

    Owner report 2026-10-26 ("снова все метрики из camera режима" on a folder
    opened before): older builds pinned the series offer, and a pin hit returned
    it without a call, so the judge was never asked again. Only a judge answer
    may be replayed now.
    """
    cache = ProfileCache(tmp_path)
    items = _evidence_items()
    offered = profile_select.derive_profile(items, mode="camera")
    assert offered.source != "vlm", "the fixture must hold a LOCAL pin"
    cache.put(
        profile_cache.profile_cache_key(
            items, mode="camera", model="m", base_url="http://x",
            reasoning_effort="auto",
        ),
        offered,
    )
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _chat(_COMPLETE_AXES)

    profile = choose_profile_sync(
        items, mode="camera", settings=_settings(), cache=cache, client_call=_client
    )
    assert calls, "a local pin must not skip the paid axis-naming call"
    assert profile is not None and profile.source == "vlm"
