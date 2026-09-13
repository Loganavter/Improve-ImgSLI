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