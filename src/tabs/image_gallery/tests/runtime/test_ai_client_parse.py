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


def test_parse_missing_delimiters_falls_back_to_full_text():
    raw = {"choices": [{"message": {"content": "just a plain description"}}]}
    result = parse_response(raw, model="test/model")
    assert result.description == "just a plain description"
    assert result.tags == ()


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


def test_parse_malformed_json_falls_back_to_lines():
    raw = {"choices": [{"message": {"content": "not json at all"}}]}
    r = parse_response(raw, model="m")
    assert r.description == "not json at all"
    assert r.verdict == "unknown"


def test_build_request_injects_measured_metrics(tmp_path):
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    payload = build_request(
        img, model="m", metrics={"sharpness": 200.0, "noise": 0.2}
    )
    text = payload["messages"][0]["content"][0]["text"]
    assert "MEASURED METRICS (authoritative):" in text
    assert "- Sharpness: 200 (quality 50%)" in text
    assert "- Clean: 0.2 (quality 80%)" in text


def test_build_request_without_metrics_has_no_block(tmp_path):
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    payload = build_request(img, model="m")
    text = payload["messages"][0]["content"][0]["text"]
    assert "MEASURED METRICS" not in text