"""Single source of truth for gallery quality (use_cases/quality).

Dots and report rows must agree on the same item: one normalization, one
mode mapping, one writer. Regression: three bespoke normalizations drifted
(card dots vs Banding/Halo rows vs triage).
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_gallery.models import Artifact, Severity
from tabs.image_gallery.use_cases import quality as q


def _item(artifacts=None, metrics=None, **kwargs):
    return SimpleNamespace(
        artifacts=dict(artifacts or {}), metrics=dict(metrics or {}), **kwargs
    )


def test_normalize_key_variants() -> None:
    assert q.normalize_key(Artifact.BANDING) == "banding"
    assert q.normalize_key("Artifact.BANDING") == "banding"
    assert q.normalize_key("Halo") == "halo"
    assert q.normalize_key("over_smoothing") == "over_smoothing"


def test_normalize_severity_never_invents_clean() -> None:
    assert q.normalize_severity(Severity.FLAGGED) == "flagged"
    assert q.normalize_severity("MILD") == "mild"
    assert q.normalize_severity("clean") == "clean"
    assert q.normalize_severity("bogus") == q.UNKNOWN
    assert q.normalize_severity(None) == q.UNMEASURED


def test_normalize_mode_aliases() -> None:
    assert q.normalize_mode(None) == "fidelity"
    assert q.normalize_mode("batch") == "batch_synthetic"
    assert q.normalize_mode("CAMERA_MODE") == "camera"
    assert q.normalize_mode("unknown") == "fidelity"


def test_merge_primary_wins_mirror_fills_gaps() -> None:
    item = _item(
        artifacts={Artifact.HALO: Severity.FLAGGED},
        metrics={"artifacts": {"halo": "clean", "banding": "mild"}},
    )
    sevs = q.severities(item)
    assert sevs["halo"] == "flagged"  # primary wins
    assert sevs["banding"] == "mild"  # mirror fills gaps


def test_noise_amp_alias() -> None:
    item = _item(metrics={"artifacts": {"noise_amp": "mild"}})
    assert q.severity(item, "noise_amplification") == "mild"


def test_severity_metric_fallbacks() -> None:
    assert q.severity(_item(metrics={"artifact_level": "flagged"}), "halo") == "flagged"
    assert q.severity(_item(metrics={"banding_score": 0.8}), "banding") == "flagged"
    assert q.severity(_item(metrics={"banding_score": 0.5}), "banding") == "mild"
    assert q.severity(_item(metrics={"banding_score": 0.1}), "banding") == "clean"
    # No data at all is "not measured" — not the optimistic "clean".
    assert q.severity(_item(), "halo") == q.UNMEASURED
    assert q.severity(_item(artifacts={"halo": "severe"}), "halo") == q.UNKNOWN


def test_aggregate_legacy_rule() -> None:
    assert q.aggregate_severity(_item(metrics={"sharpness": 50})) == "flagged"
    assert q.aggregate_severity(_item(metrics={"ssim": 0.5})) == "flagged"
    assert q.aggregate_severity(_item(metrics={"artifact_level": "mild"})) == "mild"
    assert q.aggregate_severity(_item()) == q.UNMEASURED


def test_mode_triplet_camera_and_fidelity() -> None:
    item = _item(
        artifacts={
            Artifact.NOISE_AMPLIFICATION: Severity.MILD,
            Artifact.CHROMA_FRINGING: Severity.CLEAN,
            Artifact.HALO: Severity.FLAGGED,
            Artifact.BANDING: Severity.CLEAN,
        }
    )
    assert q.mode_triplet(item, "camera") == ("mild", "clean", "flagged")
    # Blocking was never measured: the third slot is not "clean".
    assert q.mode_triplet(item, "fidelity") == ("clean", "flagged", q.UNMEASURED)


def test_mode_triplet_empty_catalog_uses_aggregate() -> None:
    item = _item(metrics={"sharpness": 10})
    assert q.mode_triplet(item, "camera") == ("flagged", "flagged", "flagged")


def test_dots_and_report_agree() -> None:
    """The reported halo row and the camera dots halo must match."""
    item = _item(
        artifacts={Artifact.HALO: Severity.FLAGGED, Artifact.BANDING: Severity.CLEAN}
    )
    triplet = q.mode_triplet(item, "camera")
    assert triplet[2] == q.severity(item, "halo") == "flagged"
    assert q.severity(item, "banding") == "clean"


def test_set_artifacts_writes_primary_and_mirror() -> None:
    item = _item()
    assert q.set_artifacts(item, {Artifact.HALO: Severity.MILD, "banding": "flagged"}) is True
    assert item.artifacts[Artifact.HALO] == Severity.MILD
    assert item.metrics["artifacts"] == {"halo": "mild", "banding": "flagged"}


def test_set_artifacts_rejects_garbage() -> None:
    item = _item()
    assert q.set_artifacts(item, {}) is False
    assert q.set_artifacts(item, None) is False  # type: ignore[arg-type]
    assert item.artifacts == {}


def test_artifacts_equal_skip_logic() -> None:
    item = _item()
    q.set_artifacts(item, {Artifact.HALO: "flagged"})
    assert q.artifacts_equal(item, {Artifact.HALO: Severity.FLAGGED}) is True
    assert q.artifacts_equal(item, {"halo": "flagged"}) is True
    assert q.artifacts_equal(item, {Artifact.HALO: Severity.MILD}) is False
def test_set_metrics_merges_and_reports_change() -> None:
    item = _item()
    assert q.set_metrics(item, {"sharpness": 210.0, "exposure": 0.48}) is True
    assert item.metrics["sharpness"] == 210.0
    assert q.set_metrics(item, {"sharpness": 210.0, "exposure": 0.48}) is False
    assert q.set_metrics(item, {"sharpness": 220.0}) is True
    assert item.metrics["sharpness"] == 220.0


def test_set_metrics_skips_garbage() -> None:
    item = _item()
    assert q.set_metrics(item, {"sharpness": "n/a", "exposure": 0.5}) is True
    assert "sharpness" not in item.metrics
    assert item.metrics["exposure"] == 0.5
    assert q.set_metrics(item, {}) is False
