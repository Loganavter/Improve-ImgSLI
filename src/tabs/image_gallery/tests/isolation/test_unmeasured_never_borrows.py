"""The "not measured" token never borrows the other backend's data.

Backend isolation (``plan-gallery-free-axes`` W5): when the active domain did
not measure an artifact, the read boundary says ``UNMEASURED`` — it must not
fill the hole from the other domain's store, from a neighbour, or from the
optimistic ``clean`` default. This is the artifact-side counterpart of
``test_ai_read_never_borrows_local_records``.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiDefect,
    Artifact,
    GalleryItem,
    Severity,
)
from tabs.image_gallery.services import quality_read
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


def test_algorithms_read_never_borrows_the_ai_defect() -> None:
    item = _item(
        analysis=_analysis(defects=(AiDefect(kind="halo", severity="flagged"),)),
    )
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="algorithms")
        == quality_read.UNMEASURED
    )
    assert quality_read.domain_artifact_severity(item, "halo", domain="ai") == "flagged"


def test_ai_read_never_borrows_the_local_artifact() -> None:
    item = _item(analysis=_analysis())
    quality.set_artifacts(item, {Artifact.HALO: Severity.FLAGGED})
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="ai")
        == quality_read.UNMEASURED
    )
    assert (
        quality_read.domain_artifact_severity(item, "halo", domain="algorithms")
        == "flagged"
    )


def test_unmeasured_is_not_clean_or_algorithms() -> None:
    unmeasured = quality_read.UNMEASURED
    assert unmeasured != "clean"
    assert unmeasured != "algorithms"
    assert unmeasured == quality.UNMEASURED
    # A bogus domain is refused, never silently served by Algorithms.
    try:
        quality_read.normalize_domain("algoritms")
    except ValueError:
        pass
    else:  # pragma: no cover - the refusal is the assertion
        raise AssertionError("normalize_domain coerced an unknown domain")
