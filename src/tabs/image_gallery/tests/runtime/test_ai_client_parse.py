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