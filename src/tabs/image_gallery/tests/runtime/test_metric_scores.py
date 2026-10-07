"""Canonical metric scores: raw → 0-100 quality, higher always better."""

from __future__ import annotations

from tabs.image_gallery.services import metric_scores as ms


def test_positive_labels_and_higher_is_better():
    # Noise renamed to its positive sense; not lower-better raw.
    spec = ms.spec_for("noise")
    assert spec is not None and spec.label == "Clean"
    assert ms.score_for(spec, 0.0) == 100
    assert ms.score_for(spec, 1.0) == 0
    clipping = ms.spec_for("clipping")
    assert clipping is not None and clipping.label == "Highlight detail"
    assert ms.score_for(clipping, 0.0) == 100
    assert ms.score_for(clipping, 10.0) == 0


def test_exposure_is_targeted_at_half():
    spec = ms.spec_for("exposure")
    assert ms.score_for(spec, 0.5) == 100
    assert ms.score_for(spec, 0.0) == 0
    assert ms.score_for(spec, 1.0) == 0
    assert ms.score_for(spec, 0.25) == 50


def test_sharpness_normalized_and_clamped():
    spec = ms.spec_for("sharpness")
    assert ms.score_for(spec, 0.0) == 0
    assert ms.score_for(spec, 200.0) == 50
    assert ms.score_for(spec, 400.0) == 100
    assert ms.score_for(spec, 999.0) == 100  # clamped


def test_aliases_resolve_first_present_key():
    spec = ms.spec_for("noise")
    assert ms.raw_for(spec, {"noise_estimate": 0.3}) == ("noise_estimate", 0.3)
    assert ms.raw_for(spec, {"noise": 0.3, "noise_estimate": 0.9}) == ("noise", 0.3)
    assert ms.raw_for(spec, {}) is None


def test_measured_scores_order_and_gaps():
    rows = ms.measured_scores({"sharpness": 200.0, "noise": 0.2})
    ids = [r[0] for r in rows]
    assert ids == ["sharpness", "noise"]  # report order
    assert rows[0][1] == "Sharpness" and rows[1][1] == "Clean"


def test_bands():
    assert ms.score_band(100) == "good"
    assert ms.score_band(70) == "good"
    assert ms.score_band(69) == "mid"
    assert ms.score_band(40) == "mid"
    assert ms.score_band(39) == "bad"


def test_prompt_block_has_label_raw_and_quality():
    text = ms.format_measured_for_prompt({"sharpness": 200.0, "noise": 0.2})
    assert "- Sharpness: 200 (quality 50%)" in text
    assert "- Clean: 0.2 (quality 80%)" in text
