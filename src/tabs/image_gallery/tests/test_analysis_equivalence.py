"""W7/W8: the dark-launch engine reproduces the legacy numbers, exactly.

Two halves:

1. **Value equivalence.** For synthetic PIL images (a gradient, a posterized
   ramp over its smooth source) the records the resolver + runner produce must
   equal the legacy values — not merely be "present": camera/fidelity are
   compared to ``metric_scores.measured_scores(<legacy dict>)`` (the one raw→0..100
   mapping the report already shows), and the artifact catalog to
   ``artifacts.analyze_images(proxy, source)`` — the aggregate the production
   stage actually calls — mapped through the same ``clean=0 / mild=1 /
   flagged=2`` rank the producer declares.
2. **Flag isolation.** With ``IMGSLI_ANALYSIS_ENGINE`` unset, the proxy entry is
   the legacy dict with no ``analysis`` key; with the flag on, the only change
   is that added key (every legacy stage value stays byte-for-byte equal).

W8 note (the gap W7's dark launch exposed): the artifact records are compared to
the *aggregate*, never to the seven ``detect_*`` functions one-to-one. The
aggregate layers ``_anchor_severity`` over the four absolute detectors
(banding/halo/blocking/chroma_fringing) when a source is present, so a
per-detector producer can disagree with ``entry["artifacts"]`` on those axes. The
with-source case below asserts the fixture actually exercises that delta
(otherwise the equality would be vacuous) and would fail against the unanchored
detectors with the concrete rank diff.
"""

from __future__ import annotations

import pytest

from engine.analysis.registry import discover
from engine.analysis.resolver import resolve_plan

from tabs.image_gallery.analysis.context_builder import build_context
from tabs.image_gallery.analysis.runner import run_plan
from tabs.image_gallery.services import (
    artifacts,
    camera_metrics,
    fidelity_metrics,
    metric_scores,
)
from tabs.image_gallery.services.proxy import clear_proxy_cache, run_proxy_stages_sync

PRODUCERS = "tabs.image_gallery.analysis.producers"

CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance")
FIDELITY_AXES = (
    "ssim",
    "detail_gain",
    "color_accuracy",
    "clipping_delta",
    "halo_delta",
    "chroma_fringe_delta",
)
ARTIFACT_AXES = (
    "banding",
    "blocking",
    "chroma_fringing",
    "halo",
    "invented_texture",
    "noise_amplification",
    "over_smoothing",
)
#: The four absolute detectors the aggregate anchors against the source; the
#: other three consume the source directly in both forms.
ANCHORED = ("banding", "halo", "blocking", "chroma_fringing")
#: The order ``artifact_catalog`` declares (and therefore returns) — the
#: manifest's reading order, not alphabetical. ``ARTIFACT_AXES`` is the same set
#: in the alphabetical order the resolver/spec lists use.
CATALOG_AXES = (
    "banding",
    "halo",
    "blocking",
    "chroma_fringing",
    "invented_texture",
    "noise_amplification",
    "over_smoothing",
)
#: Direct detector per axis — the unanchored answer a per-detector producer
#: would have reported. Kept for the non-vacuity assertion below, NOT as the
#: expected value.
DIRECT_DETECTORS = {
    "banding": artifacts.detect_banding,
    "blocking": artifacts.detect_blocking,
    "chroma_fringing": artifacts.detect_chroma_fringing,
    "halo": artifacts.detect_halo,
    "invented_texture": artifacts.detect_invented_texture,
    "noise_amplification": artifacts.detect_noise_amplification,
    "over_smoothing": artifacts.detect_over_smoothing,
}
#: The producer's declared flag rank — a candidate flag, not a quality score.
SEVERITY_RANK = {"clean": 0.0, "mild": 1.0, "flagged": 2.0}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _gradient(size: int = 96):
    from PIL import Image

    image = Image.new("RGB", (size, size))
    pixels = image.load()
    span = max(2 * (size - 1), 1)
    for y in range(size):
        for x in range(size):
            value = int((x + y) * 255 / span)
            pixels[x, y] = (value, value, value)
    return image


def _source_variant(image):
    """A blurred copy: a real reference, different enough to move every delta."""
    from PIL import ImageFilter

    return image.filter(ImageFilter.GaussianBlur(1.2))


def _banded_pair(size: int = 128, levels: int = 6):
    """A posterized ramp over its smooth original: a realistic banded candidate.

    Chosen because the aggregate's anchored severities differ from the
    unanchored detectors here (a known delta, so the equality below cannot pass
    vacuously) and because the source-relative axes split across all ranks.
    """
    import numpy as np
    from PIL import Image

    ramp = np.tile(np.linspace(40, 220, size), (size, 1))
    step = 255 // levels
    quantized = (np.round(ramp / step) * step).clip(0, 255)
    smooth = Image.fromarray(ramp.astype(np.uint8)).convert("RGB")
    banded = Image.fromarray(quantized.astype(np.uint8)).convert("RGB")
    return banded, smooth


def _records(image, source, axes) -> tuple:
    """Run the engine's local plan for *axes* over the two decoded images."""
    capabilities = {"images"} | ({"reference"} if source is not None else set())
    ctx = build_context(
        "item.png",
        proxy_image=image,
        source_image=source,
        capabilities=capabilities,
    )
    resolution = resolve_plan(
        discover(PRODUCERS),
        policy="local",
        axes=axes,
        capabilities=ctx.capabilities,
    )
    records, _journal = run_plan(resolution, {"item.png": ctx})
    return records["item.png"]


def _ok_values(records) -> dict[str, float]:
    return {
        record.axis: record.value
        for record in records
        if record.status == "ok"
    }


def _measured(metrics: dict) -> dict[str, float]:
    """The legacy report numbers for *metrics*, as ``{axis: score}``."""
    return {
        axis: float(score)
        for axis, _label, _raw, score in metric_scores.measured_scores(metrics)
    }


def _severity_rank(severity) -> float:
    return SEVERITY_RANK[str(getattr(severity, "value", severity))]


# ---------------------------------------------------------------------------
# measured axes: exact score equality with metric_scores.measured_scores
# ---------------------------------------------------------------------------


def test_camera_records_equal_the_legacy_measured_scores():
    image = _gradient()

    records = _records(image, None, CAMERA_AXES)

    expected = _measured(camera_metrics.measure_camera_from_image(image))
    assert expected, "the fixture must produce measurable camera scalars"
    assert _ok_values(records) == expected
    # Every axis the legacy report lacks is a gap in the engine, never a 0.
    gapped = {record.axis for record in records if record.status == "gap"}
    assert gapped == set(CAMERA_AXES) - set(expected)


def test_fidelity_records_equal_the_legacy_measured_scores_with_a_source():
    image = _gradient()
    source = _source_variant(image)

    records = _records(image, source, FIDELITY_AXES)

    expected = _measured(
        fidelity_metrics.compute_fidelity_from_images(image, source)
    )
    assert expected, "the fixture must produce measurable fidelity deltas"
    assert _ok_values(records) == expected
    gapped = {record.axis for record in records if record.status == "gap"}
    assert gapped == set(FIDELITY_AXES) - set(expected)


# ---------------------------------------------------------------------------
# artifact flags: exact equality with the legacy AGGREGATE (not the detectors)
# ---------------------------------------------------------------------------


def test_artifact_catalog_records_equal_the_aggregate_with_a_source():
    image, source = _banded_pair()

    records = _records(image, source, ARTIFACT_AXES)

    expected = {
        artifact.value: _severity_rank(severity)
        for artifact, severity in artifacts.analyze_images(image, source).items()
    }
    assert len(expected) == 7
    assert tuple(record.axis for record in records) == CATALOG_AXES
    assert all(record.status == "ok" for record in records), [
        (record.axis, record.status, record.reason)
        for record in records
        if record.status != "ok"
    ]
    assert all(record.producer == "local" for record in records)
    assert _ok_values(records) == expected, (
        "the engine's artifact catalog must equal artifacts.analyze_images(...), "
        "including the source-anchoring delta:\n"
        f"engine:   {_ok_values(records)}\n"
        f"aggregate:{expected}"
    )

    # Non-vacuity: the fixture must move at least one anchored axis away from
    # what the unanchored detector reports, or the assertion above would pass
    # even if the producer ignored the source (the W7 gap).
    direct = {axis: _severity_rank(DIRECT_DETECTORS[axis](image)) for axis in ARTIFACT_AXES}
    anchored_delta = {
        axis: (direct[axis], expected[axis])
        for axis in ANCHORED
        if direct[axis] != expected[axis]
    }
    assert anchored_delta, (
        "fixture does not exercise the anchoring delta: comparing against "
        f"detect_* would pass. direct={direct}, aggregate={expected}"
    )


def test_artifact_catalog_records_equal_the_sourceless_aggregate():
    """No source: the aggregate calls every detector directly — same records."""
    image = _gradient()

    records = _records(image, None, ARTIFACT_AXES)

    expected = {
        artifact.value: _severity_rank(severity)
        for artifact, severity in artifacts.analyze_images(image).items()
    }
    assert len(expected) == 7
    assert _ok_values(records) == expected, (
        f"engine: {_ok_values(records)}\naggregate: {expected}"
    )
    assert tuple(record.axis for record in records) == CATALOG_AXES
    assert all(record.status == "ok" for record in records)


# ---------------------------------------------------------------------------
# the proxy hook: flag-off byte identity, flag-on additive only
# ---------------------------------------------------------------------------


class _Item:
    """The minimal item shape ``run_proxy_stages_sync`` reads."""

    def __init__(self, path) -> None:
        self.path = path


def _write_pair(tmp_path):
    image = _gradient(64)
    item = tmp_path / "item.png"
    source = tmp_path / "source.png"
    image.save(item)
    _source_variant(image).save(source)
    return item, source


def _run_stages(item, source):
    from types import SimpleNamespace

    clear_proxy_cache()
    out = run_proxy_stages_sync(
        [SimpleNamespace(path=item)],
        source,
        include_camera=True,
    )
    assert tuple(out) == (str(item),)
    return out[str(item)]


def test_flag_off_returns_the_legacy_dict_without_an_analysis_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    item, source = _write_pair(tmp_path)

    entry = _run_stages(item, source)

    assert "analysis" not in entry, (
        "the flag-off path must not grow an analysis key (W8 flips the read path)"
    )
    # The payload is the legacy computation over the shared decoded proxies,
    # compared key by key to the stage functions the proxy already calls.
    from tabs.image_gallery.services.proxy import proxy_for

    proxy = proxy_for(item)
    source_proxy = proxy_for(source)
    assert entry["artifacts"] == artifacts.analyze_images(
        proxy.image, source_proxy.image
    )
    assert entry["camera"] == camera_metrics.measure_camera_from_image(
        proxy.image
    )
    assert entry["fidelity"] == fidelity_metrics.compute_fidelity_from_images(
        proxy.image,
        source_proxy.image,
        item_size=proxy.size,
        source_size=source_proxy.size,
    )
    assert set(entry) <= {"artifacts", "artifact_maps", "fidelity", "camera"}


def test_flag_on_adds_only_the_analysis_records(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    item, source = _write_pair(tmp_path)
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    legacy = _run_stages(item, source)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched = _run_stages(item, source)

    assert set(launched) == set(legacy) | {"analysis"}
    assert {
        key: value for key, value in launched.items() if key != "analysis"
    } == legacy, "the dark-launch hook must not alter any legacy stage value"

    records = launched["analysis"]
    axes = {record.axis for record in records}
    assert axes >= set(CAMERA_AXES) | set(ARTIFACT_AXES)
    # A source is present, so the reference producer ran too.
    assert axes >= set(FIDELITY_AXES)
    assert all(record.producer in {"local"} for record in records)
    # Dark-launch values equal the legacy stage dicts the same run produced —
    # measured axes exactly, and ALL seven artifacts exactly against the
    # aggregate (source anchoring included; W8 closed the four-axis gap).
    values = _ok_values(records)
    assert {axis: values[axis] for axis in CAMERA_AXES if axis in values} == _measured(
        legacy["camera"]
    )
    assert {axis: values[axis] for axis in FIDELITY_AXES if axis in values} == _measured(
        legacy["fidelity"]
    )
    assert {axis: values[axis] for axis in ARTIFACT_AXES} == {
        axis: _severity_rank(legacy["artifacts"][artifacts.Artifact(axis)])
        for axis in ARTIFACT_AXES
    }
