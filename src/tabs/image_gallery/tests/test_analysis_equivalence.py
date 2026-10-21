"""W7/W8/W12: the engine reproduces the legacy numbers — and now computes them once.

Three parts:

1. **Value equivalence.** For synthetic PIL images (a gradient, a posterized
   ramp over its smooth source) the records the resolver + runner produce must
   equal the legacy values — not merely be "present": camera/fidelity are
   compared to ``metric_scores.measured_scores(<legacy dict>)`` (the one raw→0..100
   mapping the report already shows), and the artifact catalog to
   ``artifacts.analyze_images(proxy, source)`` — the aggregate the production
   stage actually calls — mapped through the same ``clean=0 / mild=1 /
   flagged=2`` rank the producer declares.
2. **Flag isolation.** With ``IMGSLI_ANALYSIS_ENGINE`` unset, the proxy entry is
   the legacy dict with no ``analysis`` key; with the flag on, the entry is the
   same dict plus that key.
3. **W12 — one computation.** The measured 2.4x came from the engine and the
   legacy stages each running the same detectors. The flag-ON path now runs the
   engine FIRST and rebuilds ``artifacts``/``fidelity``/``camera`` from the
   records' pre-score ``raw`` values, so: zero legacy Stage-2 calls, exactly one
   detector pass per item, a rebuilt entry equal to the flag-OFF one (same keys,
   same values, same ``Severity`` objects), and a per-stage fail-open when a
   producer raises.

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
    # ``raw`` carries the same rank ``value`` scores: that is what lets the proxy
    # rebuild ``{Artifact: Severity}`` without a second catalog run (W12).
    assert all(record.raw == record.value for record in records)

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


def _run_stages(item, source=None):
    from types import SimpleNamespace

    clear_proxy_cache()
    out = run_proxy_stages_sync(
        [SimpleNamespace(path=item)],
        source,
        include_camera=True,
    )
    assert tuple(out) == (str(item),)
    return out[str(item)]


def _tiled_stages(item, source=None):
    """Same call with the production full-resolution artifact catalog."""
    from types import SimpleNamespace

    clear_proxy_cache()
    out = run_proxy_stages_sync(
        [SimpleNamespace(path=item)],
        source,
        include_camera=True,
        full_res_artifacts=True,
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


# ---------------------------------------------------------------------------
# W12: the engine is the SINGLE computation, the legacy stages are rebuilt
# ---------------------------------------------------------------------------

#: Module whose legacy Stage-2 calls W12 removed from the flag-ON path.
PROXY_MODULE = "tabs.image_gallery.services.proxy"


class _SeamCalls:
    """Call counts for the three legacy Stage-2 seams.

    ``total`` counts every call (the detector pass, whoever makes it) and
    ``legacy`` counts only the calls made BY ``services.proxy`` — the stage code
    the dedupe removes. Both are needed: "zero legacy calls" alone would pass if
    the engine never ran, and the detector total proves the pass happened once.
    """

    def __init__(self) -> None:
        self.total = {"artifacts": 0, "camera": 0, "fidelity": 0}
        self.legacy = {"artifacts": 0, "camera": 0, "fidelity": 0}


def _seam_calls(monkeypatch: pytest.MonkeyPatch) -> _SeamCalls:
    """Count the legacy seams; the caller module decides ``total`` vs ``legacy``."""
    import sys

    calls = _SeamCalls()

    def _patch(module, name: str, stage: str) -> None:
        real = getattr(module, name)

        def counted(*a, **kw):
            calls.total[stage] += 1
            if sys._getframe(1).f_globals.get("__name__") == PROXY_MODULE:
                calls.legacy[stage] += 1
            return real(*a, **kw)

        monkeypatch.setattr(module, name, counted)

    _patch(camera_metrics, "measure_camera_from_image", "camera")
    _patch(fidelity_metrics, "compute_fidelity_from_images", "fidelity")
    _patch(artifacts, "analyze_images", "artifacts")
    return calls


@pytest.mark.parametrize("with_source", [False, True], ids=["sourceless", "source"])
def test_flag_on_runs_each_detector_once_and_no_legacy_stage(
    tmp_path, monkeypatch: pytest.MonkeyPatch, with_source: bool
):
    """The core assertion of W12: no double work, one detector pass per item."""
    item, source = _write_pair(tmp_path)
    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    calls = _seam_calls(monkeypatch)

    entry = _run_stages(item, source if with_source else None)

    assert calls.legacy == {"artifacts": 0, "camera": 0, "fidelity": 0}, (
        "services.proxy must not call a legacy Stage-2 detector when the engine "
        f"ran — that call IS the 2.4x duplicate (counts: {calls.total})"
    )
    assert calls.total == {
        "artifacts": 1,
        "camera": 1,
        "fidelity": 1 if with_source else 0,
    }, "the detectors must run exactly once per item (the engine's pass only)"
    assert set(entry) >= {"artifacts", "camera", "analysis"}
    if with_source:
        assert "fidelity" in entry


@pytest.mark.parametrize("with_source", [False, True], ids=["sourceless", "source"])
def test_flag_on_entry_equals_the_flag_off_entry(
    tmp_path, monkeypatch: pytest.MonkeyPatch, with_source: bool
):
    """The rebuild is not "close": same keys, same values, same Severity objects."""
    item, source = _write_pair(tmp_path)
    src = source if with_source else None
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    legacy = _run_stages(item, src)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched = _run_stages(item, src)

    assert set(launched) == set(legacy) | {"analysis"}
    rebuilt = {key: value for key, value in launched.items() if key != "analysis"}
    assert rebuilt == legacy
    # The artifacts are the SAME enum members the aggregate returned — a rebuilt
    # rank that produced equal-but-different values would be a silent swap.
    for artifact, severity in legacy["artifacts"].items():
        assert rebuilt["artifacts"][artifact] is severity
    # And the records behind them are what the read path sees (W9).
    assert launched["analysis"] and all(
        record.producer == "local" for record in launched["analysis"]
    )


def test_flag_on_falls_back_to_the_legacy_stage_when_a_producer_raises(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """A raising producer costs its OWN legacy call — never a missing stage."""
    from tabs.image_gallery.analysis import runner
    from tabs.image_gallery.services.proxy import proxy_for

    item, source = _write_pair(tmp_path)

    def _boom(_ctx):
        raise RuntimeError("synthetic producer failure")

    # The runner caches each producer's ``run`` after the first plan: patch the
    # cache slot too, or an earlier test leaves the real callable in place.
    monkeypatch.setitem(runner._RUN_FUNCS, "fidelity_reference", _boom)
    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    calls = _seam_calls(monkeypatch)

    entry = _run_stages(item, source)

    assert calls.legacy == {"artifacts": 0, "camera": 0, "fidelity": 1}
    assert set(entry) >= {"artifacts", "fidelity", "camera", "analysis"}
    proxy = proxy_for(item)
    source_proxy = proxy_for(source)
    assert entry["fidelity"] == fidelity_metrics.compute_fidelity_from_images(
        proxy.image,
        source_proxy.image,
        item_size=proxy.size,
        source_size=source_proxy.size,
    )
    failed = {record.axis: record.status for record in entry["analysis"]}
    assert failed["ssim"] == "error", "the failing producer must be recorded, not hidden"


def test_flag_on_rebuilds_the_learned_keys_into_their_legacy_dicts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """BRISQUE belongs to the camera dict, LPIPS/DISTS to the fidelity dict.

    The learned backend needs torch, so the seam is stubbed: both paths call the
    same stub, and the rebuilt entry must still place each key in the dict the
    legacy services put it in (``camera_metrics`` appends BRISQUE,
    ``fidelity_metrics`` appends the pair).
    """
    from tabs.image_gallery.services import quality_models

    monkeypatch.setattr(
        quality_models, "pair_metrics", lambda item, src, **_kw: {"lpips": 0.31, "dists": 0.22}
    )
    monkeypatch.setattr(quality_models, "nr_metrics", lambda image, **_kw: {"brisque": 12.5})
    item, source = _write_pair(tmp_path)
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    legacy = _run_stages(item, source)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched = _run_stages(item, source)

    assert legacy["camera"]["brisque"] == 12.5
    assert legacy["fidelity"]["lpips"] == 0.31
    assert legacy["fidelity"]["dists"] == 0.22
    assert {k: v for k, v in launched.items() if k != "analysis"} == legacy


def test_producers_carry_the_pre_score_detector_value():
    """``raw`` is the detector value the score came from — not a second score."""
    image = _gradient()

    records = _records(image, None, CAMERA_AXES)

    measured = {record.axis: record for record in records if record.status == "ok"}
    expected = camera_metrics.measure_camera_from_image(image)
    assert measured, "the fixture must produce measurable camera scalars"
    for axis, record in measured.items():
        spec = metric_scores.spec_for(axis)
        raw = metric_scores.raw_for(spec, expected)[1]
        assert record.raw == raw
        assert metric_scores.score_for(spec, record.raw) == record.value
    # A gap is a gap: no borrowed raw value either.
    assert all(record.raw is None for record in records if record.status == "gap")


def _blocky_pair(size: tuple[int, int] = (1600, 1200), offset: int = 24):
    """8x8 DCT-like blocks: a proxy decode misses the grid, the tiled one does not."""
    import numpy as np
    from PIL import Image

    width, height = size
    x = np.arange(width)
    ramp = x % 8
    bx = x // 8
    by = np.arange(height) // 8
    dc = ((bx[None, :] + by[:, None]) % 2) * offset
    base = np.clip(ramp[None, :] + dc, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([base, base, base]), "RGB")


def test_flag_on_falls_back_to_the_tiled_catalog_in_full_res_mode(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """``full_res_artifacts`` stays the tiled catalog: different pixels, not a dupe.

    The dedupe must never substitute the proxy severities for the full-resolution
    ones (the 8x8 blocking grid would vanish), so this mode rebuilds fidelity and
    camera from records and keeps the tiled artifacts.
    """
    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_gradient(96)).save(source)
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    proxy_mode = _run_stages(item)
    legacy = _tiled_stages(item)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched = _tiled_stages(item)

    assert {k: v for k, v in launched.items() if k != "analysis"} == legacy
    assert "analysis" in launched
    # Non-vacuity: on this fixture the tiled catalog and the proxy catalog differ,
    # so the equality above would fail if the rebuild leaked proxy severities in.
    assert legacy["artifacts"] != proxy_mode["artifacts"]

    # With a reference the production shape is the same: fidelity comes from the
    # records, artifacts still from the tiled store.
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    legacy_src = _tiled_stages(item, source)
    proxy_src = _run_stages(item, source)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched_src = _tiled_stages(item, source)

    assert {k: v for k, v in launched_src.items() if k != "analysis"} == legacy_src
    assert legacy_src["artifacts"] != proxy_src["artifacts"]


def test_flag_on_same_file_pair_keeps_the_identity_fidelity(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """A same-file pair writes identity scores in both modes (no pair call)."""
    item, _source = _write_pair(tmp_path)
    monkeypatch.delenv("IMGSLI_ANALYSIS_ENGINE", raising=False)
    legacy = _run_stages(item, item)

    monkeypatch.setenv("IMGSLI_ANALYSIS_ENGINE", "1")
    launched = _run_stages(item, item)

    assert legacy["fidelity"] == {
        "ssim": 1.0,
        "hf_ratio": 0.0,
        "delta_e": 0.0,
        "upscale_factor": 1,
    }
    assert {k: v for k, v in launched.items() if k != "analysis"} == legacy

