from __future__ import annotations

import pytest

from tabs.image_gallery.services.ai_client import AiResponseError, parse_response


def test_parse_well_formed_response():
    raw = {
        "choices": [
            {
                "message": {
                    "content": "DESCRIPTION: A cat on a windowsill.\nTAGS: cat, window, sunlight"
                }
            }
        ]
    }
    result = parse_response(raw, model="test/model")
    assert result.description == "A cat on a windowsill."
    assert result.tags == ("cat", "window", "sunlight")
    assert result.model == "test/model"
    assert result.analyzed_at_iso


def test_parse_missing_delimiters_raises():
    """Free-form text without the contract is rejected, not shown."""
    raw = {"choices": [{"message": {"content": "just a plain description"}}]}
    with pytest.raises(AiResponseError):
        parse_response(raw, model="test/model")


def test_parse_missing_choices_raises():
    with pytest.raises(AiResponseError):
        parse_response({}, model="test/model")


def test_parse_empty_content_raises():
    raw = {"choices": [{"message": {"content": "   "}}]}
    with pytest.raises(AiResponseError):
        parse_response(raw, model="test/model")


def _quality_content() -> str:
    return (
        "SHARPNESS: 85\n"
        "NOISE: 90\n"
        "EXPOSURE: 78\n"
        "COMPOSITION: 80\n"
        "VERDICT: keep\n"
        "REASON: Clean and sharp.\n"
        "DESCRIPTION: A cat on a sofa.\n"
        "TAGS: cat, sofa"
    )


def test_parse_quality_format_scores_and_verdict():
    from tabs.image_gallery.models import ai_quality_score

    raw = {"choices": [{"message": {"content": _quality_content()}}]}
    result = parse_response(raw, model="test/model")
    assert (result.sharpness, result.noise, result.exposure, result.composition) == (85, 90, 78, 80)
    assert result.verdict == "keep"
    assert result.verdict_reason == "Clean and sharp."
    assert result.description == "A cat on a sofa."
    assert result.tags == ("cat", "sofa")
    assert ai_quality_score(result) == pytest.approx((85 + 90 + 78 + 80) / 4)


def test_parse_scores_clamped_and_verdict_normalized():
    raw = {
        "choices": [
            {
                "message": {
                    "content": "SHARPNESS: 140\nNOISE: -5\nEXPOSURE: 72%\nCOMPOSITION: n/a\n"
                    "VERDICT: REJECTED!\nREASON: blurry\nDESCRIPTION: x\nTAGS: y"
                }
            }
        ]
    }
    result = parse_response(raw, model="test/model")
    assert (result.sharpness, result.noise, result.exposure, result.composition) == (100, 0, 72, -1)
    assert result.verdict == "reject"


def test_parse_legacy_caption_only_leaves_quality_unknown():
    from tabs.image_gallery.models import ai_quality_score

    raw = {
        "choices": [
            {
                "message": {
                    "content": "DESCRIPTION: A cat on a windowsill.\nTAGS: cat, window, sunlight"
                }
            }
        ]
    }
    result = parse_response(raw, model="test/model")
    assert (result.sharpness, result.noise, result.exposure, result.composition) == (-1, -1, -1, -1)
    assert result.verdict == "unknown"
    assert result.verdict_reason == ""
    assert ai_quality_score(result) is None


def test_ai_quality_score_partial_axes():
    from tabs.image_gallery.models import AiAnalysisResult, ai_quality_score

    r = AiAnalysisResult(description="d", tags=(), model="m", analyzed_at_iso="t", sharpness=80)
    assert ai_quality_score(r) == pytest.approx(80.0)
    assert ai_quality_score(None) is None


def _json_reply(obj) -> dict:
    import json as _json

    return {"choices": [{"message": {"content": _json.dumps(obj)}}]}


def test_parse_json_contract_verdict_defects_confidence():
    raw = _json_reply(
        {
            "verdict": "reject",
            "reason": "Strong halo on edges.",
            "defects": [
                {"kind": "halo", "severity": "flagged", "note": "edge glow"},
                {"kind": "Band'ing", "severity": "mild"},
                {"kind": "bogus_kind", "severity": "mild"},
                {"kind": "noise", "severity": "clean"},  # dropped: not a defect
            ],
            "composition": 72,
            "confidence": 0.85,
        }
    )
    r = parse_response(raw, model="m")
    assert r.verdict == "reject"
    assert r.verdict_reason == "Strong halo on edges."
    assert r.composition == 72
    assert r.confidence == pytest.approx(0.85)
    kinds = [d.kind for d in r.defects]
    assert kinds == ["halo", "other", "other"]  # unknown kinds → "other", clean dropped
    assert r.defects[0].severity == "flagged"
    # Scene caption is not part of the new contract.
    assert r.description == "" and r.tags == ()


def test_parse_json_in_code_fences_and_prose():
    content = 'Sure!\n```json\n{"verdict": "keep", "reason": "ok", "defects": []}\n```'
    raw = {"choices": [{"message": {"content": content}}]}
    r = parse_response(raw, model="m")
    assert r.verdict == "keep"
    assert r.defects == ()
    assert r.composition == -1


def test_parse_freeform_prose_raises_instead_of_dumping_cot():
    """A reasoning dump with no JSON and no legacy markers must NOT be shown.

    Regression: the model answered with chain-of-thought prose; the block
    displayed it verbatim. Now it is a clean parse error.
    """
    cot = (
        "Let me analyze the measured metrics:\n"
        "- Sharpness: 253 (quality 63%) - moderate\n"
        "Let me think about other potential defects:\n"
        "- No obvious halos"
    )
    raw = {"choices": [{"message": {"content": cot}}]}
    with pytest.raises(AiResponseError):
        parse_response(raw, model="m")


def test_parse_legacy_line_format_still_falls_back():
    raw = {"choices": [{"message": {"content": "DESCRIPTION: a cat\nTAGS: cat, sofa"}}]}
    r = parse_response(raw, model="m")
    assert r.description == "a cat"
    assert r.tags == ("cat", "sofa")


def test_parse_axis_notes_normalized_to_known_ids():
    raw = _json_reply(
        {
            "verdict": "keep",
            "reason": "ok",
            "defects": [],
            "axis_notes": {
                "noise": "coarse film grain",
                "sharpness": "  soft, mushy edges  ",
                "bogus_axis": "x",
                "halo": "",
            },
        }
    )
    r = parse_response(raw, model="m")
    assert r.axis_notes == {
        "noise": "coarse film grain",
        "sharpness": "soft, mushy edges",
    }


def test_parse_strips_reasoning_block_before_json():
    content = (
        " thinkingLet me reason about sharpness and noise...<｜end▁of▁thinking｜>"
        '{"verdict": "keep", "reason": "ok", "defects": []}'
    )
    raw = {"choices": [{"message": {"content": content}}]}
    r = parse_response(raw, model="m")
    assert r.verdict == "keep"


def test_ratelimit_headers_compact():
    from tabs.image_gallery.services.ai_client import _ratelimit_headers

    h = {
        "X-RateLimit-Limit": "20",
        "X-RateLimit-Remaining": "0",
        "Retry-After": "30",
        "X-Request-Id": "abc",
        "Content-Type": "application/json",
    }
    s = _ratelimit_headers(h)
    assert "x-ratelimit-limit=20" in s
    assert "x-ratelimit-remaining=0" in s
    assert "retry-after=30" in s
    assert "x-request-id=abc" in s
    assert "content-type" not in s


def test_build_request_forces_json_and_hides_reasoning_on_openrouter(tmp_path):
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    p = build_request(img, model="m", openrouter=True)
    assert p["response_format"] == {"type": "json_object"}
    assert p["reasoning"] == {"effort": "low", "exclude": True}
    assert p["provider"]["require_parameters"] is True
    assert p["provider"]["allow_fallbacks"] is True
    # Default fallback chain, primary first, no duplicate.
    assert p["models"] == ["m", "z-ai/glm-5.3-flash", "openai/gpt-6-luna"]
    assert p["route"] == "fallback"
    p2 = build_request(img, model="m")
    assert p2["response_format"] == {"type": "json_object"}
    assert "reasoning" not in p2
    assert "provider" not in p2
    assert "models" not in p2


def test_build_request_fallback_chain_no_duplicate_and_override(tmp_path):
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    # Primary already in the defaults → not repeated.
    p = build_request(img, model="openai/gpt-6-luna", openrouter=True)
    assert p["models"] == ["openai/gpt-6-luna", "z-ai/glm-5.3-flash"]
    # Explicit override wins.
    p2 = build_request(
        img, model="a", openrouter=True, fallback_models=("b", "c", "a")
    )
    assert p2["models"] == ["a", "b", "c"]


def test_build_request_never_echoes_a_judged_axis(tmp_path):
    """P3-E: the local number for a judged axis is NOT handed to the model.

    Red-before (live 2026-10-21): the prompt carried
    "LOCAL MEASUREMENTS (Algorithms domain, context only)" with the local number
    for every axis the model was asked to score, and the model answered a
    constant ``exposure = 82`` on five of six cards — an echo, not a judgement.
    ``sharpness`` and ``noise`` are BOTH in the asked set for the no-mode prompt,
    so neither line may survive.
    """
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    payload = build_request(
        img, model="m", metrics={"sharpness": 200.0, "noise": 0.2}
    )
    text = payload["messages"][0]["content"][0]["text"]
    assert "LOCAL MEASUREMENTS" not in text
    assert "quality 50%" not in text and "quality 80%" not in text


def test_build_request_keeps_a_measurement_for_an_axis_it_does_not_judge(tmp_path):
    """The filter is not "drop the block": a reference/photo axis the prompt does
    not ask about may still ride along as context."""
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    payload = build_request(img, model="m", metrics={"brisque": 30.0})
    text = payload["messages"][0]["content"][0]["text"]
    assert "LOCAL MEASUREMENTS" in text
    assert "- Naturalness: 30 (quality" in text
    assert '"brisque"' not in text.split("LOCAL MEASUREMENTS")[0], (
        "brisque must not be in the asked axis set for the no-mode prompt"
    )


def test_build_request_without_metrics_has_no_block(tmp_path):
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    payload = build_request(img, model="m")
    text = payload["messages"][0]["content"][0]["text"]
    assert "LOCAL MEASUREMENTS" not in text


def test_build_request_requests_every_axis_for_mode(tmp_path):
    """A1: the prompt asks for one score per applicable axis for the mode."""
    from tabs.image_gallery.services.ai_client import build_request
    from tabs.image_gallery.services.rank_fusion import measured_axes_for

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    for mode in ("camera", "fidelity", "batch_synthetic"):
        payload = build_request(img, model="m", mode=mode)
        text = payload["messages"][0]["content"][0]["text"]
        for axis_id in measured_axes_for(mode):
            assert f'"{axis_id}"' in text, (mode, axis_id)
        assert '"axes"' in text
    # Fidelity also asks for the reference axes; camera asks for BRISQUE.
    fidelity = build_request(img, model="m", mode="fidelity")["messages"][0]["content"][0]["text"]
    camera = build_request(img, model="m", mode="camera")["messages"][0]["content"][0]["text"]
    assert '"ssim"' in fidelity and '"brisque"' in camera
    assert '"ssim"' not in camera
    # composition stays a separate top-level field.
    assert '"composition": <0-100>' in fidelity


def test_parse_json_axes_scorecard():
    """A1: an open ``axes`` scorecard parses, unknown ids dropped."""
    from tabs.image_gallery.models import ai_axis_score

    raw = _json_reply(
        {
            "axes": {"sharpness": 81, "ssim": 55, "bogus_axis": 10, "noise": 140},
            "verdict": "keep",
            "reason": "ok",
        }
    )
    r = parse_response(raw, model="m")
    assert r.axes == {"sharpness": 81, "ssim": 55, "noise": 100}
    assert ai_axis_score(r, "sharpness") == 81
    assert ai_axis_score(r, "ssim") == 55
    assert ai_axis_score(r, "exposure") == -1


def test_parse_named_fields_merge_into_scorecard():
    """An old prompt's named fields fill the same open scorecard."""
    raw = _json_reply({"sharpness": 70, "composition": 60, "verdict": "keep"})
    r = parse_response(raw, model="m")
    assert r.axes.get("sharpness") == 70
    assert r.axes.get("composition") == 60
    assert r.sharpness == 70 and r.composition == 60


# --- extended AI-backend trace (IMGSLI_AI_DEBUG) ---------------------------


def test_ai_snippet_is_bounded_head_and_tail() -> None:
    from tabs.image_gallery.services.ai_client import _ai_snippet

    s = _ai_snippet("A" * 5000)
    assert s.startswith("(5000c) ")
    assert "…" in s and len(s) < 1200
    assert _ai_snippet("hi") == "(2c) hi"
    assert _ai_snippet(None) == "(0c) "


def test_parse_failure_trace_reports_finish_and_content(caplog, monkeypatch) -> None:
    """On an unparseable reply the trace must name finish_reason + the content.

    A truncated answer (finish_reason=length) is the classic consistent
    parse failure; the [ai] trace now shows it instead of a bare error.
    """
    import logging

    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    raw = {
        "model": "m",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": '{"axes": {"sharpness": 8'},
            }
        ],
    }
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        with pytest.raises(AiResponseError):
            parse_response(raw, model="m")
    assert "parse NO-JSON" in caplog.text
    assert "finish=length" in caplog.text
    assert "content=(" in caplog.text


def test_parse_trace_reports_reasoning_and_json(caplog, monkeypatch) -> None:
    import json as _json
    import logging

    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    _reasoning = "<thinking>x</thinking>"
    content = _reasoning + " scratchpad clearly reasoning about quality<｜end▁of▁thinking｜>" + _json.dumps(
        {"verdict": "keep", "reason": "ok"}
    )
    raw = {"choices": [{"message": {"content": content}}]}
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        parse_response(raw, model="m")
    assert "think=True" in caplog.text
    assert "json_found=True" in caplog.text


def test_parse_trace_silent_without_key(caplog, monkeypatch) -> None:
    import logging

    monkeypatch.delenv("IMGSLI_AI_DEBUG", raising=False)
    raw = {"choices": [{"message": {"content": "prose that is not json"}}]}
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        with pytest.raises(AiResponseError):
            parse_response(raw, model="m")
    assert "[ai]" not in caplog.text


def test_transport_trace_logs_finish_usage_and_content(caplog, monkeypatch) -> None:
    """The transport summary shows finish_reason / usage / content snippet."""
    import io
    import logging

    import tabs.image_gallery.services.ai_client.transport as tr

    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    body = b"".join(
        [
            b'data: {"model":"m","choices":[{"delta":{"content":"{\\"verdict\\":\\"keep\\"}"}}]}\n\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"total_tokens":42}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    class _Resp(io.BytesIO):
        status = 200
        headers: dict = {}

    monkeypatch.setattr(
        tr.urllib.request, "urlopen", lambda req, timeout=None: _Resp(body)
    )
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        raw = tr.call_sync("https://x/api/v1", "key", {"model": "m", "messages": []})
    assert raw["choices"][0]["finish_reason"] == "stop"
    assert "response model=m finish=stop" in caplog.text
    assert "content_chars=" in caplog.text
    assert "total_tokens" in caplog.text
    assert "body_bytes=" in caplog.text


# --- reasoning effort + budget (the recurring truncation fix) --------------


def test_build_request_applies_user_reasoning_effort(tmp_path) -> None:
    """The scorecard request must send the user's effort (auto -> safe floor).

    Regression: the analyze path dropped ``reasoning_effort`` entirely and sent
    a bare ``{"exclude": True}`` at the model's DEFAULT effort (max for
    glm-5.3-flash) with a hardcoded 900-token cap — hidden reasoning ate the
    budget and the JSON was truncated.
    """
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    auto = build_request(img, model="m", openrouter=True)
    assert auto["reasoning"] == {"effort": "low", "exclude": True}
    high = build_request(img, model="m", openrouter=True, reasoning_effort="high")
    assert high["reasoning"]["effort"] == "high"
    # Budget from the shared estimator, never below the old 900 floor.
    assert auto["max_tokens"] >= 900
    assert high["max_tokens"] >= auto["max_tokens"]
    # An explicit max_tokens override wins.
    assert build_request(img, model="m", max_tokens=2048)["max_tokens"] == 2048
    # No reasoning param off OpenRouter (plain OpenAI API).
    assert "reasoning" not in build_request(img, model="m")


def test_parse_truncated_answer_raises_distinct_error() -> None:
    """finish_reason=length surfaces as AiTruncatedError (still an AiResponseError)."""
    from tabs.image_gallery.services.ai_client import AiResponseError, AiTruncatedError

    raw = {
        "choices": [
            {"finish_reason": "length", "message": {"content": '{"axes": {"sharp'}}
        ]
    }
    with pytest.raises(AiTruncatedError):
        parse_response(raw, model="m")
    assert issubclass(AiTruncatedError, AiResponseError)


def test_analyze_forwards_reasoning_effort_into_the_request(tmp_path, monkeypatch) -> None:
    import tabs.image_gallery.services.ai_client as ai_client

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    seen: dict = {}

    def _fake_call(base_url, api_key, payload, **kw):
        seen["payload"] = payload
        return {
            "choices": [
                {"message": {"content": '{"verdict": "keep", "axes": {"sharpness": 80}}'}}
            ]
        }

    monkeypatch.setattr(ai_client, "call_sync", _fake_call)
    ai_client.analyze_image_sync(
        img,
        base_url="https://openrouter.ai/api/v1",
        api_key="k",
        model="m",
        reasoning_effort="high",
    )
    assert seen["payload"]["reasoning"] == {"effort": "high", "exclude": True}
    assert seen["payload"]["max_tokens"] >= 900

