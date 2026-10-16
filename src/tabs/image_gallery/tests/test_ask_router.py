"""A2 — ``ask_router`` routing, payload shape, and fail-open answers.

No network: the transport is injected (or ``call_sync`` monkeypatched). The
router enforces the backend contract — text questions carry NO image bytes,
visual questions do, routing questions degrade visibly (Jev stub).
"""

from __future__ import annotations

import pytest

from tabs.image_gallery.services import ask_router
from tabs.image_gallery.services.ask_router import (
    BACKEND_JEV,
    BACKEND_TEXT,
    BACKEND_VLM,
    AskResult,
    answer,
    build_text_payload,
    build_vision_payload,
    resolve_backend,
    route_backend,
)

_CTX = {
    "kind": "selection",
    "label": "Selection",
    "count": 1,
    "mode": "fidelity",
    "source": None,
    "items": [
        {
            "name": "a.png",
            "alias": "img_1",
            "path": "/g/a.png",
            "metrics": {"sharpness": 50},
            "severities": {"banding": "mild"},
            "badge": "★",
        }
    ],
    "names": {"img_1": "a.png"},
    "metric_labels": {"sharpness": "Sharpness"},
}


def _system_text(payload: dict) -> str:
    return payload["messages"][0]["content"][0]["text"]


def _user_text(payload: dict) -> str:
    return payload["messages"][-1]["content"][0]["text"]


def test_empty_question_routes_to_text():
    assert route_backend("", _CTX) == BACKEND_TEXT
    assert route_backend("Summary", _CTX) == BACKEND_TEXT


def test_visual_question_routes_to_vlm():
    assert route_backend("what is visually wrong here?", _CTX) == BACKEND_VLM
    assert route_backend("describe the color", _CTX) == BACKEND_VLM


def test_routing_question_routes_to_jev():
    assert route_backend("prioritize this series", _CTX) == BACKEND_JEV
    assert route_backend("which series should I route first?", _CTX) == BACKEND_JEV


def test_text_payload_has_no_image_bytes():
    payload = build_text_payload("Summary", _CTX, model="m")
    assert payload["messages"][0]["role"] == "system"
    assert all(m["role"] != "tool" for m in payload["messages"])
    assert "image_url" not in repr(payload)


def test_text_payload_uses_opaque_alias_not_filename():
    payload = build_text_payload("Summary", _CTX, model="m")
    text = _user_text(payload)
    assert "img_1" in text
    assert "a.png" not in text
    assert "label" in _system_text(payload).lower()


def test_context_block_uses_labels_and_descriptors_not_raw_ids():
    payload = build_text_payload("Summary", _CTX, model="m")
    user = _user_text(payload)
    # Human label + band descriptor, never the bare metric id.
    assert "Sharpness 50%" in user
    assert "sharpness=50" not in user
    # The instructions live in the system turn: no number recital, no preamble.
    system = _system_text(payload).lower()
    assert "percentages" in system
    assert "preamble" in system
    assert "photographer" not in system


def test_text_payload_has_system_role_and_fewshot():
    payload = build_text_payload("Summary", _CTX, model="m")
    roles = [m["role"] for m in payload["messages"]]
    assert roles[0] == "system"
    assert "assistant" in roles  # the few-shot exemplar
    assert roles[-1] == "user"


def test_context_block_renders_artifact_severities_with_meaning():
    ctx = {
        "count": 1,
        "metric_labels": {},
        "items": [{"alias": "img_1", "metrics": {}, "severities": {"banding": "flagged"}}],
    }
    text = _user_text(build_text_payload("x", ctx, model="m"))
    assert "banding:flagged" in text
    assert "visible banding" in text  # severity gets a meaning, not just the id


def test_context_block_falls_back_to_id_when_no_labels():
    ctx = {"count": 1, "items": [{"metrics": {"sharpness": 50}}]}
    text = _user_text(build_text_payload("Summary", ctx, model="m"))
    assert "Sharpness 50%" not in text  # no label map → id used
    assert "sharpness 50%" in text


def test_vision_payload_embeds_downscaled_image(monkeypatch):
    from tabs.image_gallery.services import ask_payload

    monkeypatch.setattr(ask_payload, "_encode_image", lambda p: ("png", "QUJD"))
    payload = build_vision_payload("what is wrong?", _CTX, model="m")
    content = payload["messages"][-1]["content"]
    assert content[0]["type"] == "text"
    assert any(
        part["type"] == "image_url" and "data:image/png;base64,QUJD" in part["image_url"]["url"]
        for part in content
    )


def test_vision_payload_sends_an_image_for_every_scope_item(monkeypatch):
    from tabs.image_gallery.services import ask_payload

    monkeypatch.setattr(ask_payload, "_encode_image", lambda p: ("png", "QUJD"))
    items = [
        {"alias": f"img_{i}", "name": f"{i}.png", "path": f"/g/{i}.png", "metrics": {}}
        for i in range(1, 9)
    ]
    ctx = {**_CTX, "count": len(items), "items": items}
    payload = build_vision_payload("what is wrong?", ctx, model="m")
    parts = [p for p in payload["messages"][-1]["content"] if p["type"] == "image_url"]
    assert len(parts) == 8


def test_answer_text_uses_transport_and_returns_text():
    captured = {}

    def fake_transport(base_url, api_key, payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Looks clean."}}]}

    result = answer(
        "Summary",
        _CTX,
        backend=BACKEND_TEXT,
        base_url="http://x",
        api_key="k",
        model="m",
        transport=fake_transport,
    )
    assert isinstance(result, AskResult)
    assert result.text == "Looks clean."
    assert result.backend == BACKEND_TEXT
    assert "image_url" not in repr(captured["payload"])


def test_answer_vlm_routes_images(monkeypatch):
    from tabs.image_gallery.services import ask_payload

    monkeypatch.setattr(ask_payload, "_encode_image", lambda p: ("png", "QUJD"))
    captured = {}

    def fake_transport(base_url, api_key, payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "Blurry edges."}}]}

    result = answer(
        "what is wrong?",
        _CTX,
        backend=BACKEND_VLM,
        base_url="http://x",
        api_key="k",
        model="m",
        transport=fake_transport,
    )
    assert result.text == "Blurry edges."
    assert "image_url" in repr(captured["payload"])


def test_answer_jev_stub_degrades_visibly_without_fabricating():
    def boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("transport must not be reached for the Jev stub")

    result = answer(
        "prioritize",
        _CTX,
        backend=BACKEND_JEV,
        base_url="http://x",
        api_key="k",
        model="m",
        transport=boom,
    )
    assert result.text == ""
    assert result.error
    assert "routing" in result.error.lower()


def test_resolve_backend_honors_include_images_toggle():
    q = "describe the color"
    assert resolve_backend(q, _CTX, include_images=None) == BACKEND_VLM  # auto
    assert resolve_backend(q, _CTX, include_images=True) == BACKEND_VLM
    assert resolve_backend(q, _CTX, include_images=False) == BACKEND_TEXT  # metrics only


def test_resolve_backend_include_images_forces_vlm_for_text_question():
    assert resolve_backend("Summary", _CTX, include_images=True) == BACKEND_VLM
    assert resolve_backend("Summary", _CTX, include_images=False) == BACKEND_TEXT


def test_resolve_backend_never_overrides_routing():
    assert resolve_backend("prioritize this series", _CTX, include_images=True) == BACKEND_JEV
    assert resolve_backend("prioritize this series", _CTX, include_images=False) == BACKEND_JEV


def test_extract_text_accepts_parts_list():
    raw = {
        "choices": [
            {"message": {"content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]}}
        ]
    }
    assert ask_router._extract_text(raw) == "hello world"


def test_extract_text_empty_content_is_an_error():
    raw = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    with pytest.raises(ask_router.AiResponseError):
        ask_router._extract_text(raw)


def test_openrouter_caps_reasoning_effort_and_raises_budget():
    """Mandatory-reasoning models default to effort `max`; we must cap it low."""
    payload = ask_router._apply_openrouter_extensions(
        {"model": "m", "messages": []}, "https://openrouter.ai/api/v1", "m"
    )
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["provider"]["sort"] == "throughput"
    assert "m" in payload["models"]


def test_openrouter_extensions_noop_for_plain_openai():
    payload = ask_router._apply_openrouter_extensions(
        {"model": "m", "messages": []}, "https://api.openai.com/v1", "m"
    )
    assert "reasoning" not in payload
    assert "provider" not in payload


def test_answer_openrouter_payload_caps_reasoning_and_sizes_budget():
    captured = {}

    def fake_transport(base_url, api_key, payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ok"}}]}

    answer(
        "Summary",
        _CTX,
        backend=BACKEND_TEXT,
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        model="m",
        transport=fake_transport,
    )
    payload = captured["payload"]
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_tokens"] >= 512


def test_resolve_reasoning_effort_collapses_auto_and_none_to_low():
    assert ask_router.resolve_reasoning_effort("auto") == "low"
    assert ask_router.resolve_reasoning_effort("") == "low"
    assert ask_router.resolve_reasoning_effort("none") == "low"
    assert ask_router.resolve_reasoning_effort("medium") == "medium"
    assert ask_router.resolve_reasoning_effort("high") == "high"


def test_estimate_budget_scales_with_scope_size():
    small = ask_router.estimate_ask_max_tokens({"count": 1}, effort="auto")
    big = ask_router.estimate_ask_max_tokens({"count": 100}, effort="auto")
    assert small >= 512
    assert big > small * 2
    assert big <= 16384


def test_estimate_budget_configured_override_wins():
    assert ask_router.estimate_ask_max_tokens({"count": 100}, configured=1234) == 1234


def test_estimate_budget_reasoning_headroom():
    low = ask_router.estimate_ask_max_tokens({"count": 50}, effort="low")
    high = ask_router.estimate_ask_max_tokens({"count": 50}, effort="high")
    assert high > low


def test_answer_not_configured_is_a_visible_error():
    result = answer("Summary", _CTX, backend=BACKEND_TEXT, transport=lambda *a: {})
    assert result.text == ""
    assert result.error


def test_answer_backend_exception_yields_error_result():
    def failing(base_url, api_key, payload):
        raise RuntimeError("network exploded")

    result = answer(
        "Summary",
        _CTX,
        backend=BACKEND_TEXT,
        base_url="http://x",
        api_key="k",
        model="m",
        transport=failing,
    )
    assert result.text == ""
    assert "exploded" in result.error


def test_answer_parses_json_envelope_and_confidence():
    def fake(base_url, api_key, payload):
        return {"choices": [{"message": {"content": '{"answer": "Prefer img_1.", "confidence": "high"}'}}]}

    result = answer(
        "Summary", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert result.text == "Prefer img_1."
    assert result.confidence == 0.9
    assert result.revised is False


def test_answer_falls_back_to_raw_when_not_enveloped():
    def fake(base_url, api_key, payload):
        return {"choices": [{"message": {"content": "Prefer img_1, it is clean."}}]}

    result = answer(
        "Summary", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert result.text == "Prefer img_1, it is clean."


def test_guard_triggers_one_rewrite_on_number_recital():
    calls: list[dict] = []

    def fake(base_url, api_key, payload):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": '{"answer": "img_1 is 88% vs img_2 71%.", "confidence": "high"}'}}]}
        return {"choices": [{"message": {"content": '{"answer": "Prefer img_1: it is the cleanest; img_2 is softer.", "confidence": "high"}'}}]}

    result = answer(
        "Summary", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert len(calls) == 2
    assert result.revised is True
    assert "88%" not in result.text
    # the rewrite carried the previous answer + feedback in the user turn
    assert "REVISION REQUEST" in calls[1]["messages"][-1]["content"][0]["text"]


def test_guard_numeric_question_allows_numbers_and_skips_rewrite():
    calls: list[dict] = []

    def fake(base_url, api_key, payload):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"answer": "img_1 scores 88.", "confidence": "high"}'}}]}

    result = answer(
        "give me the sharpness numbers", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert len(calls) == 1
    assert result.revised is False


def test_guard_still_violating_rewrite_keeps_original():
    calls: list[dict] = []

    def fake(base_url, api_key, payload):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"answer": "img_1 is 88%.", "confidence": "high"}'}}]}

    result = answer(
        "Summary", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert len(calls) == 2
    assert result.revised is False
    assert result.text == "img_1 is 88%."


_FLAG_CTX = {
    **_CTX,
    "items": [
        {
            **_CTX["items"][0],
            "flags": [
                {"id": "halo_delta", "label": "Halo vs source", "kind": "candidate", "note": ""},
                {"id": "flag-for-review", "label": "odd", "kind": "judgment", "note": ""},
            ],
        }
    ],
}


def test_system_prompt_separates_measured_numbers_from_ai_flags():
    text = _system_text(build_text_payload("Summary", _CTX, model="m")).lower()
    assert "ground truth" in text
    assert "unverified ai flags" in text
    assert "never as a number" in text


def test_context_block_appends_ai_flags_as_text_with_legend():
    user = _user_text(build_text_payload("Summary", _FLAG_CTX, model="m"))
    assert "Axis kinds: measured = a number" in user
    assert "AI flags: possible Halo vs source; AI judgment: odd" in user
    assert "Sharpness 50%" in user  # measured score is still rendered as before
    assert "possible Halo vs source%" not in user


def test_context_block_has_no_legend_without_flags():
    user = _user_text(build_text_payload("Summary", _CTX, model="m"))
    assert "Axis kinds" not in user
    assert "AI flags" not in user


def test_flagged_context_still_routes_text_question_to_text_payload():
    assert route_backend("Summary", _FLAG_CTX) == BACKEND_TEXT
    assert resolve_backend("Summary", _FLAG_CTX, include_images=None) == BACKEND_TEXT
    payload = build_text_payload("Summary", _FLAG_CTX, model="m")
    assert "image_url" not in repr(payload)


def test_guard_rewrites_candidate_flag_stated_as_percent():
    calls: list[dict] = []

    def fake(base_url, api_key, payload):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": '{"answer": "img_1 has a possible halo at 60%.", "confidence": "high"}'}}]}
        return {"choices": [{"message": {"content": '{"answer": "Prefer img_1, but watch for a possible halo.", "confidence": "medium"}'}}]}

    result = answer(
        "Summary", _FLAG_CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert len(calls) == 2
    assert result.revised is True
    assert "60%" not in result.text
    assert "possible halo" in result.text


def test_guard_rewrite_error_is_fail_open():
    calls: list[dict] = []

    def fake(base_url, api_key, payload):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": '{"answer": "img_1 is 88%.", "confidence": "high"}'}}]}
        raise RuntimeError("network blip")

    result = answer(
        "Summary", _CTX, backend=BACKEND_TEXT,
        base_url="http://x", api_key="k", model="m", transport=fake,
    )
    assert result.revised is False
    assert result.text == "img_1 is 88%."
