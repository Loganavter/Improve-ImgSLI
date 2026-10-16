"""A2 seam: the per-domain quality read (``services/quality_read``).

The AI domain reads the VLM's scorecard/defects; the Algorithms domain reads
the local detectors. Neither may silently fall back to the other
(plan-gallery-ai-backend-owns-quality-2026-10-16).
"""

from __future__ import annotations

import json
from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult, AiDefect, GalleryItem
from tabs.image_gallery.services import quality_read


def _item(**kwargs) -> GalleryItem:
    item = GalleryItem(path=Path(kwargs.pop("name", "a.png")), mtime_ns=1)
    for key, value in kwargs.items():
        setattr(item, key, value)
    return item


def _analysis(**kwargs) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", **kwargs
    )


def test_ai_domain_reads_only_the_analysis():
    item = _item(
        metrics={"sharpness": 200.0, "noise": 0.9},
        analysis=_analysis(axes={"sharpness": 33, "noise": 91}, composition=44),
    )
    read = quality_read.domain_axis_scores(item, domain="ai")
    assert read == {"sharpness": 33, "noise": 91, "composition": 44}
    # The detector values (50% / 10%) must not leak in.
    assert 50 not in read.values()


def test_algorithms_domain_reads_only_the_detectors():
    item = _item(
        metrics={"sharpness": 200.0, "noise": 0.9},
        analysis=_analysis(axes={"sharpness": 33, "noise": 91}),
    )
    read = quality_read.domain_axis_scores(item, domain="algorithms")
    assert read.get("sharpness") == 50  # 200 / 400 quality
    assert read.get("noise") == 10  # lower-is-better
    assert 33 not in read.values()  # the VLM number must not leak in


def test_unknown_domain_degrades_to_algorithms():
    item = _item(metrics={"sharpness": 200.0})
    assert quality_read.normalize_domain(None) == "algorithms"
    assert quality_read.normalize_domain("weird") == "algorithms"
    assert quality_read.domain_axis_scores(item, domain=None) == {"sharpness": 50}


def test_ai_artifact_severities_from_defects_worst_wins():
    item = _item(
        analysis=_analysis(
            defects=(
                AiDefect(kind="halo", severity="mild"),
                AiDefect(kind="halo", severity="flagged"),
                AiDefect(kind="noise", severity="mild"),  # → noise_amplification
                AiDefect(kind="clipping", severity="flagged"),  # no artifact row
            )
        )
    )
    sev = quality_read.ai_artifact_severities(item)
    assert sev == {"halo": "flagged", "noise_amplification": "mild"}


def test_domain_artifact_severity_switches_read():
    from tabs.image_gallery.models import Artifact, Severity
    from tabs.image_gallery.use_cases import quality

    item = _item(
        analysis=_analysis(defects=(AiDefect(kind="halo", severity="flagged"),)),
    )
    quality.set_artifacts(item, {Artifact.HALO: Severity.MILD})
    assert quality_read.domain_artifact_severity(item, "halo", domain="ai") == "flagged"
    assert quality_read.domain_artifact_severity(item, "halo", domain="algorithms") == "mild"


def test_ai_domain_unanalyzed_is_empty_not_detector_fallback():
    item = _item(metrics={"sharpness": 200.0})  # measured, never analyzed
    assert quality_read.domain_axis_scores(item, domain="ai") == {}
    assert quality_read.domain_artifact_severity(item, "halo", domain="ai") == "clean"


def test_ai_read_survives_parse_to_read_with_distinct_values():
    """A5 content: distinct per-axis VLM values survive parse → read (not counts)."""
    from tabs.image_gallery.services.ai_client import parse_response

    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "axes": {"sharpness": 11, "noise": 22, "exposure": 33},
                            "composition": 44,
                            "verdict": "keep",
                        }
                    )
                }
            }
        ]
    }
    result = parse_response(payload, model="m")
    item = _item(analysis=result, metrics={"sharpness": 999.0, "noise": 0.0})
    read = quality_read.domain_axis_scores(item, domain="ai")
    assert read == {"sharpness": 11, "noise": 22, "exposure": 33, "composition": 44}
    # Identity, not presence: the four payloads are distinguishable.
    assert len(set(read.values())) == len(read)
