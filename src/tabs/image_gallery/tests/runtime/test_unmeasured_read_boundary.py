"""Read boundary: "not measured" is a value, never the optimistic one.

``plan-gallery-free-axes`` (owner 2026-10-27). Red-before probes on the parent
tree, all four green here:

1. ``domain_artifact_severity`` on an item with no artifacts returned ``clean``;
2. a reader that raised returned ``clean``;
3. ``normalize_domain("nonsense")`` returned ``algorithms``;
4. ``score_for(spec_for("sharpness"), nan)`` returned ``0``.

The app must not invent a value: ``clean`` only from data that says clean,
``UNMEASURED`` when nothing measured, ``"unknown"`` for an unreadable token,
``None`` for a raw that is not a measurement.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiDefect,
    Artifact,
    GalleryItem,
    Severity,
)
from tabs.image_gallery.services import metric_scores, quality_read
from tabs.image_gallery.use_cases import quality


def _item(**kwargs) -> GalleryItem:
    item = GalleryItem(path=Path(kwargs.pop("name", "a.png")), mtime_ns=1)
    for key, value in kwargs.items():
        setattr(item, key, value)
    return item


def _analysis(**kwargs) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", **kwargs
    )


def test_absent_artifact_is_unmeasured_not_clean() -> None:
    item = _item(metrics={"sharpness": 200.0})
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="algorithms")
        == quality_read.UNMEASURED
    )
    assert quality.severity(item, "halo") == quality.UNMEASURED


def test_ai_absent_defect_and_missing_analysis_are_unmeasured() -> None:
    analyzed = _item(analysis=_analysis())
    assert (
        quality_read.domain_artifact_severity(analyzed, "halo", domain="ai")
        == quality_read.UNMEASURED
    )
    # No analysis blob at all: a different cause, the same honest answer.
    assert (
        quality_read.domain_artifact_severity(_item(), "halo", domain="ai")
        == quality_read.UNMEASURED
    )


def test_raised_reader_is_unmeasured(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("reader raised")

    monkeypatch.setattr(quality, "severity", _boom)
    item = _item(artifacts={Artifact.HALO: Severity.FLAGGED})
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="algorithms")
        == quality_read.UNMEASURED
    )


def test_unknown_domain_raises_no_coercion() -> None:
    with pytest.raises(ValueError):
        quality_read.normalize_domain("nonsense")
    # A domain nobody named keeps the documented Algorithms default.
    assert quality_read.normalize_domain(None) == quality_read.ALGORITHMS_DOMAIN


def test_unknown_severity_token_is_unknown_not_clean() -> None:
    local = _item(artifacts={"halo": "severe"})
    assert quality.severity(local, "halo") == quality.UNKNOWN
    ai = _item(analysis=_analysis(defects=(AiDefect(kind="halo", severity="severe"),)))
    assert quality_read.ai_artifact_severities(ai) == {"halo": "unknown"}


def test_clean_requires_data_that_says_clean() -> None:
    item = _item()
    quality.set_artifacts(item, {Artifact.HALO: Severity.CLEAN})
    assert quality.severity(item, "halo") == "clean"
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="algorithms")
        == "clean"
    )


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf"), "n/a", None])
def test_unmeasurable_raw_scores_none_not_zero(raw) -> None:
    spec = metric_scores.spec_for("sharpness")
    assert spec is not None
    assert metric_scores.score_for(spec, raw) is None


def test_zero_is_a_real_score_and_survives() -> None:
    spec = metric_scores.spec_for("sharpness")
    assert spec is not None
    assert metric_scores.score_for(spec, 0.0) == 0


def test_unscored_dot_says_not_measured_and_paints_neutral() -> None:
    from tabs.image_gallery.ui.card.dots import (
        _neutral_color,
        _severity_color,
        dot_tooltip_text,
    )

    assert dot_tooltip_text(("Sharpness", None)) == "Sharpness: not measured"
    assert (
        _severity_color("unmeasured").name().lower()
        == _neutral_color().name().lower()
    )
    # A non-measurement is never painted with the measured-good token.
    assert (
        _severity_color(quality.UNMEASURED).name().lower()
        != _severity_color("clean").name().lower()
    )


def test_gap_axis_is_not_painted_as_a_zero() -> None:
    """A partially measured card dots only measured axes — never a 0 for a gap."""
    from tabs.image_gallery.ui.card.dots import metric_dots_for_item

    item = _item(metrics={"sharpness": 200.0})
    _colors, infos = metric_dots_for_item(item, mode="camera", domain="algorithms")
    assert ("Sharpness", 50) in infos
    assert all(score != 0 for _label, score in infos)
