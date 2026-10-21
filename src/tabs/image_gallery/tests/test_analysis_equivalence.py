"""W7/W8/W12/P9b: the engine reproduces the legacy numbers — and computes them once.

Parts:

1. **Value equivalence.** For synthetic PIL images (a gradient, a posterized
   ramp over its smooth source) the records the resolver + runner produce must
   equal the legacy values — not merely be "present": camera/fidelity are
   compared to ``metric_scores.measured_scores(<legacy dict>)`` (the one raw→0..100
   mapping the report already shows), and the artifact catalog to
   ``artifacts.analyze_images(proxy, source)`` — the aggregate the production
   stage actually calls — mapped through the same ``clean=0 / mild=1 /
   flagged=2`` rank the producer declares.
2. **No flag (P9b).** The env kill-switch is gone; the legacy branch is gone with
   it. The stage functions are still called by this module as an ORACLE
   (``_legacy_oracle``), never by the production path — every equality below is
   "the rebuilt entry equals what the legacy path answered", not "the two modes
   agree".
3. **W12 — one computation.** The measured 2.4x came from the engine and the
   legacy stages each running the same detectors. The proxy runs the engine
   FIRST and rebuilds ``artifacts``/``fidelity``/``camera`` from the records'
   pre-score ``raw`` values, so: zero legacy Stage-2 calls, exactly one detector
   pass per item, and a rebuilt entry equal to the oracle (same keys, same
   values, same ``Severity`` objects).
4. **P9b — gaps instead of fallbacks.** A producer that raises costs its stage's
   numbers (and a warning naming stage + producer), never a second measurement:
   camera/fidelity stay absent, the artifact catalog is the ONE retained
   fallback because its absence would render as ``clean``.
5. **W14 — one artifact catalog.** In ``full_res_artifacts`` mode (the
   production default) the entry's artifacts come from the TILED catalog, while
   the records used to come from the bounded proxy: two catalogs, two answers
   for the same flag (the proxy cannot see the 8x8 block grid). The proxy now
   hands the engine the same full-resolution store, so the records ARE the
   entry's severities and the tiled runner runs exactly once.
6. **W13 — one learned pass.** ``compute_fidelity_from_images`` already calls
   ``quality_models.pair_metrics`` for the item/source pair. The deleted
   learned-quality producer called the same seam again for the same pair —
   identical numbers, a second torch forward pass. The count is the test: the
   local plan must reach the seam exactly once per item, and restoring a second
   caller must turn that counter red.

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

from pathlib import Path

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
    # W13: LPIPS/DISTS are fidelity axes — the same ``compute_fidelity_from_images``
    # call that produces the deltas already runs the learned pair pass.
    "lpips",
    "dists",
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
# the proxy hook: the engine's entry vs the legacy stage functions (oracle)
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


#: The one camera key no producer answers (W13 deleted the BRISQUE producer), so
#: the rebuilt dict carries a gap there rather than a substituted number.
CAMERA_WITHOUT_PRODUCER = "brisque"


def _legacy_oracle(item, source=None) -> dict:
    """The old legacy entry, computed directly from the stage functions.

    P9b deleted the proxy's legacy branch, so the detectors are called here —
    over the module's own shared proxies — to keep the equivalence gate honest:
    "the rebuild equals what the legacy path answered", never "two modes agree".
    Test-only: nothing in ``services/`` calls these any more for camera/fidelity.
    """
    from tabs.image_gallery.services.proxy import proxy_for

    proxy = proxy_for(item)
    assert proxy is not None
    src_proxy = proxy_for(source) if source is not None else None
    expected: dict = {
        "artifacts": artifacts.analyze_images(
            proxy.image, src_proxy.image if src_proxy is not None else None
        )
    }
    if src_proxy is not None:
        same = Path(source).resolve() == Path(item).resolve()
        if same:
            expected["fidelity"] = {
                "ssim": 1.0,
                "hf_ratio": 0.0,
                "delta_e": 0.0,
                "upscale_factor": 1,
            }
        else:
            expected["fidelity"] = fidelity_metrics.compute_fidelity_from_images(
                proxy.image,
                src_proxy.image,
                item_size=proxy.size,
                source_size=src_proxy.size,
            )
    expected["camera"] = camera_metrics.measure_camera_from_image(proxy.image)
    return expected


def _tiled_oracle(item, source=None) -> dict:
    """The tiled catalog the legacy path computed, over the same stores.

    Test-only oracle for W14: the production path answers artifacts from the
    engine's records, so the tiled call itself has to be invoked here to prove
    the records carry ITS severities (not the bounded proxy's).
    """
    from engine.store.tiled_pixel_store import TiledPixelStore
    from tabs.image_gallery.services.proxy import _analyze_artifacts_full_res, proxy_for

    proxy = proxy_for(item)
    assert proxy is not None
    src_proxy = proxy_for(source) if source is not None else None
    same = source is not None and Path(source).resolve() == Path(item).resolve()
    source_store = None if same or source is None else TiledPixelStore.from_path(source)
    try:
        return _analyze_artifacts_full_res(
            item,
            source_store,
            same,
            proxy.image,
            src_proxy.image if src_proxy is not None else None,
        )
    finally:
        if source_store is not None:
            source_store.close()


def _assert_rebuilt_entry(entry: dict, expected: dict) -> None:
    """The entry's stage dicts equal the oracle's — one documented gap aside.

    ``CAMERA_WITHOUT_PRODUCER`` is excluded and then asserted ABSENT from the
    entry: the legacy dict carries it only when the learned backend is installed,
    and no producer measures it (W13), so a present value would mean a legacy
    call ran — the exact thing P9b deleted.

    ``artifact_maps`` is the SalArt coarse localization overlay, not a stage:
    it is computed from whichever catalog the entry carries, so it has no oracle
    of its own here.
    """
    launched = {
        key: value
        for key, value in entry.items()
        if key not in ("analysis", "artifact_maps")
    }
    oracle = dict(expected)
    oracle_camera = dict(oracle.get("camera") or {})
    oracle_camera.pop(CAMERA_WITHOUT_PRODUCER, None)
    oracle["camera"] = oracle_camera
    assert launched == oracle
    assert CAMERA_WITHOUT_PRODUCER not in (entry.get("camera") or {}), (
        "no producer measures BRISQUE: the rebuilt camera dict must carry a gap, "
        "not a number measured by the deleted legacy call"
    )


# ---------------------------------------------------------------------------
# W12: the engine is the SINGLE computation, the legacy stages are rebuilt
# ---------------------------------------------------------------------------

#: Module whose legacy Stage-2 calls W12 removed from the path.
PROXY_MODULE = "tabs.image_gallery.services.proxy"


class _SeamCalls:
    """Call counts for the three legacy Stage-2 seams.

    ``total`` counts every call (the detector pass, whoever makes it) and
    ``legacy`` counts only the calls made BY ``services.proxy`` — the stage code
    P9b deleted. Both are needed: "zero legacy calls" alone would pass if the
    engine never ran, and the detector total proves the pass happened once.
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
def test_one_detector_pass_per_item_and_no_legacy_call(
    tmp_path, monkeypatch: pytest.MonkeyPatch, with_source: bool
):
    """W12/W13/P9b: one detector pass per item, made by the engine only.

    Artifacts, fidelity and camera are all rebuilt from the engine's records, so
    ``services.proxy`` calls no legacy stage at all (before P9b the camera dict
    came from the legacy call, and that was the last one). The totals prove the
    pass happened: exactly one per stage that has something to measure.
    """
    item, source = _write_pair(tmp_path)
    calls = _seam_calls(monkeypatch)

    entry = _run_stages(item, source if with_source else None)

    assert calls.legacy == {"artifacts": 0, "camera": 0, "fidelity": 0}, (
        "services.proxy must not call a legacy stage detector: the records are "
        f"the only path (counts: {calls.total})"
    )
    assert calls.total == {
        "artifacts": 1,
        "camera": 1,
        "fidelity": 1 if with_source else 0,
    }, "each stage's detector runs once, in the engine"
    assert set(entry) >= {"artifacts", "camera", "analysis"}
    if with_source:
        assert "fidelity" in entry


def _counting_pair(monkeypatch: pytest.MonkeyPatch, pair: dict) -> list[str]:
    """Count ``quality_models.pair_metrics`` passes — the learned seam itself.

    ``nr_metrics`` is stubbed empty as well: W13 left BRISQUE without a producer,
    and a pair-count test must not try to import torch/piq to prove its point.
    """
    from tabs.image_gallery.services import quality_models

    calls: list[str] = []

    def pair_metrics(item, source, *args, **kwargs):
        calls.append("pair")
        return dict(pair)

    monkeypatch.setattr(quality_models, "pair_metrics", pair_metrics)
    monkeypatch.setattr(quality_models, "nr_metrics", lambda *args, **kwargs: {})
    return calls


def _local_plan_item():
    image = _gradient(64)
    ctx = build_context(
        "item.png",
        proxy_image=image,
        source_image=_source_variant(image),
        capabilities={"images", "reference"},
    )
    resolution = resolve_plan(discover(PRODUCERS), policy="local")
    return resolution, {"item.png": ctx}


def test_local_plan_calls_the_pair_seam_once_per_item(
    monkeypatch: pytest.MonkeyPatch,
):
    """W13: one LPIPS/DISTS pass per item, made by the fidelity computation."""
    calls = _counting_pair(monkeypatch, {"lpips": 0.31, "dists": 0.22})
    resolution, contexts = _local_plan_item()

    records, _journal = run_plan(resolution, contexts)

    assert len(calls) == 1, (
        "the same pair must reach pair_metrics once: "
        "compute_fidelity_from_images already calls it, so a second producer "
        "means a second torch forward pass over the same two images"
    )
    by_axis = {record.axis: record for record in records["item.png"]}
    assert by_axis["lpips"].status == "ok"
    assert by_axis["dists"].status == "ok"


def test_a_second_pair_caller_turns_the_counter_red(
    monkeypatch: pytest.MonkeyPatch,
):
    """Red-before for the test above: a second caller must be visible as 2.

    This restores exactly what the deleted learned-quality producer did —
    call ``pair_metrics`` after the fidelity dict already carried the pair — in
    the runner's producer wrapper. Without this case the single-pass assertion
    could pass for the wrong reason (e.g. the seam never being reached at all).
    """
    from tabs.image_gallery.analysis import runner
    from tabs.image_gallery.analysis.producers.fidelity_reference import (
        producer as fidelity,
    )
    from tabs.image_gallery.services import quality_models

    calls = _counting_pair(monkeypatch, {"lpips": 0.31, "dists": 0.22})
    real_run = fidelity.run

    def run_and_duplicate(ctx):
        records = real_run(ctx)
        quality_models.pair_metrics(ctx.proxy_image, ctx.source_image)
        return records

    monkeypatch.setitem(runner._RUN_FUNCS, "fidelity_reference", run_and_duplicate)
    resolution, contexts = _local_plan_item()

    run_plan(resolution, contexts)

    assert len(calls) == 2, (
        "the counter must see the duplicate pair pass; a count of 1 here would "
        "mean the gate above proves nothing"
    )


@pytest.mark.parametrize("with_source", [False, True], ids=["sourceless", "source"])
def test_entry_equals_the_legacy_stage_dicts(
    tmp_path, monkeypatch: pytest.MonkeyPatch, with_source: bool
):
    """The rebuild is not "close": same keys, same values, same Severity objects.

    P9b removed the flag, so the comparison target is the stage functions
    themselves (``_legacy_oracle``), not a second proxy run.
    """
    item, source = _write_pair(tmp_path)
    src = source if with_source else None
    expected = _legacy_oracle(item, src)

    launched = _run_stages(item, src)

    _assert_rebuilt_entry(launched, expected)
    # The artifacts are the SAME enum members the aggregate returned — a rebuilt
    # rank that produced equal-but-different values would be a silent swap.
    for artifact, severity in expected["artifacts"].items():
        assert launched["artifacts"][artifact] is severity
    # And the records behind them are what the read path sees (W9).
    assert launched["analysis"] and all(
        record.producer == "local" for record in launched["analysis"]
    )


@pytest.mark.parametrize(
    ("stage", "producer", "axes"),
    [
        ("camera", "camera_scalars", CAMERA_AXES),
        ("fidelity", "fidelity_reference", FIDELITY_AXES),
    ],
    ids=["camera", "fidelity"],
)
def test_a_failing_producer_leaves_a_gap_and_never_reruns_the_detector(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    stage: str,
    producer: str,
    axes: tuple[str, ...],
):
    """P9b red-before: a producer failure costs its stage's numbers, not a legacy call.

    Before this wave the proxy caught the empty rebuild and ran
    ``measure_camera_from_image`` / ``compute_fidelity_from_images`` for the
    stage (``calls.legacy[stage] == 1``, numbers present — the two red-before
    failures are exactly those two counters). Now the entry carries no dict for
    the stage, the records carry the ``error``, and one warning names the stage
    and the producer. The other stage keeps its numbers: a gap is local.
    """
    import logging

    from tabs.image_gallery.analysis import runner

    def _boom(_ctx):
        raise RuntimeError("synthetic producer failure")

    # The runner caches each producer's ``run`` after the first plan: patch the
    # cache slot too, or an earlier test leaves the real callable in place.
    monkeypatch.setitem(runner._RUN_FUNCS, producer, _boom)
    item, source = _write_pair(tmp_path)
    calls = _seam_calls(monkeypatch)
    caplog.set_level(logging.WARNING, logger="ImproveImgSLI")

    entry = _run_stages(item, source)

    assert calls.legacy[stage] == 0, (
        f"services.proxy called the legacy {stage} detector after the producer "
        "failed: P9b deleted that fallback"
    )
    assert stage not in entry, (
        f"the {stage} dict must be absent, not repaired by a second measurement"
    )
    assert "artifacts" in entry, "a gap in one stage must not cost the catalog"
    other = "fidelity" if stage == "camera" else "camera"
    assert other in entry, "the healthy stage must keep its numbers"
    statuses = {record.axis: record.status for record in entry["analysis"]}
    assert all(statuses[axis] == "error" for axis in axes), statuses
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    stage_warnings = [m for m in messages if f"{stage} records unusable" in m]
    assert stage_warnings, f"the failure must be logged, not silent: {messages}"
    assert producer in stage_warnings[0], (
        "the warning must name the producer that failed"
    )
    assert "synthetic producer failure" in stage_warnings[0], (
        "the warning must carry the producer's own error, not just 'failed'"
    )


def test_a_sourceless_item_has_no_fidelity_stage_and_no_failure_warning(
    tmp_path, caplog
):
    """No reference is not a failure: the producer is not even in the plan.

    Structural absence must stay distinguishable from a producer that raised —
    otherwise "no source" would log a stage failure on every item of a camera
    batch, and the real failures would be lost in it.
    """
    import logging

    item, _source = _write_pair(tmp_path)
    caplog.set_level(logging.WARNING, logger="ImproveImgSLI")

    entry = _run_stages(item, None)

    assert "fidelity" not in entry
    statuses = {record.axis for record in entry["analysis"]}
    assert not statuses & set(FIDELITY_AXES), statuses
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert not any("fidelity records unusable" in m for m in messages), messages


def test_the_artifact_fallback_is_the_one_kept_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog
):
    """P9b: a broken artifact producer still yields a COMPLETE catalog.

    Red-before counterpart: the same failure with the fallback removed leaves the
    entry without ``artifacts`` — and a missing artifact entry renders as
    ``clean`` (``quality_read.domain_artifact_severity``), i.e. a producer
    failure would look like "nothing wrong". The sentinel catalog proves the
    number came from the fallback call, not from the records.
    """
    import logging

    from tabs.image_gallery.analysis import runner
    from tabs.image_gallery.models import Artifact, Severity

    def _boom(_ctx):
        raise RuntimeError("synthetic producer failure")

    monkeypatch.setitem(runner._RUN_FUNCS, "artifact_catalog", _boom)
    sentinel = {artifact: Severity.FLAGGED for artifact in Artifact}
    fallback_calls: list = []

    def _sentinel(*args, **_kw):
        fallback_calls.append(args)
        return dict(sentinel)

    monkeypatch.setattr(artifacts, "analyze_images", _sentinel)
    item, source = _write_pair(tmp_path)
    caplog.set_level(logging.WARNING, logger="ImproveImgSLI")

    entry = _run_stages(item, source)

    assert entry["artifacts"] == sentinel, (
        "the entry must carry the fallback catalog, not records that cannot "
        "describe it"
    )
    assert len(fallback_calls) == 1, (
        "the artifact catalog is the ONE retained fallback; 0 here means the "
        f"entry lost its flags, >1 means a second computation (count: {len(fallback_calls)})"
    )
    statuses = {record.axis: record.status for record in entry["analysis"]}
    assert all(statuses[axis] == "error" for axis in ARTIFACT_AXES), statuses
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert any("artifacts records unusable" in m for m in messages), messages


def test_the_rebuilt_dicts_place_the_learned_keys_where_the_services_do(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """LPIPS/DISTS belong to the fidelity dict — the learned pair, not a 2nd pass.

    The learned backend needs torch, so the seam is stubbed: the fidelity
    producer calls ``fidelity_metrics`` which calls the stub, and the rebuilt
    entry must still place each key in the dict the legacy service put it in.

    BRISQUE is deliberately NOT here: W13 deleted its producer, so the rebuilt
    camera dict cannot carry it. That is a gap (asserted below), not a reason to
    run the legacy camera call again — P9b.
    """
    from tabs.image_gallery.services import quality_models

    monkeypatch.setattr(
        quality_models, "pair_metrics", lambda item, src, **_kw: {"lpips": 0.31, "dists": 0.22}
    )
    monkeypatch.setattr(quality_models, "nr_metrics", lambda image, **_kw: {"brisque": 12.5})
    item, source = _write_pair(tmp_path)

    launched = _run_stages(item, source)

    assert launched["fidelity"]["lpips"] == 0.31
    assert launched["fidelity"]["dists"] == 0.22
    assert CAMERA_WITHOUT_PRODUCER not in launched["camera"], (
        "BRISQUE has no producer any more: it must stay a gap"
    )
    gaps = {record.axis for record in launched["analysis"] if record.status != "ok"}
    assert CAMERA_WITHOUT_PRODUCER not in gaps, (
        "the camera producer does not declare BRISQUE at all, so it is absent "
        "from the plan rather than a record"
    )


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


def _assert_records_are_the_entry(entry: dict) -> None:
    """The artifact records carry the SAME severities the entry shows, by axis."""
    records = {
        record.axis: record
        for record in entry["analysis"]
        if record.axis in ARTIFACT_AXES
    }
    assert set(records) == set(ARTIFACT_AXES)
    assert all(record.status == "ok" for record in records.values()), [
        (axis, record.status, record.reason)
        for axis, record in records.items()
        if record.status != "ok"
    ]
    for artifact, severity in entry["artifacts"].items():
        axis = getattr(artifact, "value", artifact)
        assert records[axis].raw == _severity_rank(severity), (
            "the read path prefers the records (W9), so a record whose rank "
            "differs from the entry is the W14 finding: "
            f"{axis}: record {records[axis].raw} vs entry {_severity_rank(severity)}"
        )
        # The rebuilt ``Severity`` must be the catalog's own enum member.
        assert entry["artifacts"][artifact] is severity


@pytest.mark.parametrize("with_source", [False, True], ids=["sourceless", "source"])
def test_full_res_mode_enters_the_tiled_catalog_and_its_records(
    tmp_path, with_source: bool
):
    """``full_res_artifacts``: the entry is the tiled catalog, and so are the records.

    The dedupe must never substitute the proxy severities for the full-resolution
    ones (the 8x8 blocking grid would vanish), but it also must not leave the
    records answering the proxy catalog while the entry shows the tiled one —
    the read path prefers the records, so that would show a different severity
    than the entry for the same file.
    """
    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_gradient(96)).save(source)
    src = source if with_source else None
    expected = _tiled_oracle(item, src)

    launched = _tiled_stages(item, src)

    assert launched["artifacts"] == expected
    assert "analysis" in launched
    _assert_records_are_the_entry(launched)
    # Identity, not equality: the rebuilt dict holds the same enum members.
    for artifact, severity in expected.items():
        assert launched["artifacts"][artifact] is severity
    # Non-vacuity: on this fixture the tiled catalog and the proxy catalog differ,
    # so the equality above would fail if the rebuild leaked proxy severities in.
    from tabs.image_gallery.services.proxy import proxy_for

    src_proxy = proxy_for(src) if src is not None else None
    proxy_catalog = artifacts.analyze_images(
        proxy_for(item).image, src_proxy.image if src_proxy is not None else None
    )
    assert expected != proxy_catalog


class _TiledCalls:
    """Call count of the tiled seam, split by caller module.

    ``total`` proves the catalog ran; ``by_proxy`` proves ``services.proxy`` is
    not still running its own copy of it (the W14 double work).
    """

    def __init__(self) -> None:
        self.total = 0
        self.by_proxy = 0
        self.references: list = []


def _count_tiled(monkeypatch: pytest.MonkeyPatch) -> _TiledCalls:
    """Count ``analyze_artifacts_tiled`` (resolved per call by both callers)."""
    import sys

    from tabs.image_gallery.services import artifact_tiles

    calls = _TiledCalls()
    real = artifact_tiles.analyze_artifacts_tiled

    def counted(source, *, source_image=None, **kwargs):
        calls.total += 1
        if sys._getframe(1).f_globals.get("__name__") == PROXY_MODULE:
            calls.by_proxy += 1
        try:
            calls.references.append(tuple(int(v) for v in source_image.size))
        except Exception:
            calls.references.append(None)
        return real(source, source_image=source_image, **kwargs)

    monkeypatch.setattr(artifact_tiles, "analyze_artifacts_tiled", counted)
    return calls


def test_full_res_calls_the_tiled_catalog_once(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """One tiled pass, made by the engine — never a second one by the proxy."""
    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_gradient(96)).save(source)
    calls = _count_tiled(monkeypatch)

    entry = _tiled_stages(item, source)

    assert calls.total == 1, (
        "the tiled catalog is the engine's single pass; a second one means the "
        "proxy still ran its own copy"
    )
    assert calls.by_proxy == 0, "services.proxy must not call the tiled catalog"
    _assert_records_are_the_entry(entry)
    # The reference handed to the tiles is the caller's reference for it.
    assert calls.references == [(96, 96)]


def test_the_pre_w14_shape_turns_the_seam_gate_red(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Red-before for the two gates above: the pre-W14 shape is visible.

    Restoring exactly what the tree did before this wave — the engine hook gets
    no store, and the rebuild refuses to answer artifacts in full-res mode — is
    one tiled call made BY THE PROXY, and records that disagree with the entry
    (proxy ranks vs tiled severities). ``total`` alone would not catch it (1
    either way); ``by_proxy`` is the gate, and ``_assert_records_are_the_entry``
    is the second.
    """
    from tabs.image_gallery.services import analysis_bridge

    real_engine = analysis_bridge.engine_records
    real_stage = analysis_bridge.stage_dicts_from_records

    def proxy_only_records(*args, **kwargs):
        kwargs["tiled_store"] = None
        kwargs["tiled_source_store"] = None
        return real_engine(*args, **kwargs)

    def pre_w14_rebuild(*args, **kwargs):
        kwargs["artifacts_from_records"] = False
        return real_stage(*args, **kwargs)

    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_gradient(96)).save(source)
    monkeypatch.setattr(analysis_bridge, "engine_records", proxy_only_records)
    monkeypatch.setattr(
        analysis_bridge, "stage_dicts_from_records", pre_w14_rebuild
    )
    calls = _count_tiled(monkeypatch)

    entry = _tiled_stages(item, source)

    assert calls.by_proxy == 1, (
        "the pre-W14 proxy still ran its own tiled catalog; a 0 here would mean "
        "the seam gate above proves nothing"
    )
    with pytest.raises(AssertionError, match="W14 finding"):
        _assert_records_are_the_entry(entry)


def test_full_res_anchors_on_the_full_resolution_reference(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """A tiled anchor crops item coordinates, so the reference must be full-res.

    Feeding the bounded proxy source (longest edge <= 1024) into tile-sized
    crops would anchor full-resolution tiles against downscaled pixels and
    silently report a different severity than the entry shows.
    """
    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_blocky_pair(size=(1200, 900), offset=8)).save(source)
    calls = _count_tiled(monkeypatch)
    launched = _tiled_stages(item, source)

    assert calls.total == 1
    assert calls.references == [(1200, 900)], (
        "the tiles were anchored on a downscaled reference (the proxy caps at "
        "1024): the full-resolution store must be handed to the context"
    )
    _assert_records_are_the_entry(launched)
    assert launched["artifacts"] == _tiled_oracle(item, source)


def test_a_bounded_proxy_reference_turns_the_anchor_gate_red(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Red-before: without the full-resolution reference the gate sees the cap.

    The same call with ``tiled_source_store`` dropped anchors the tiles on
    ``ctx.source_image`` — the bounded proxy (longest edge 1024) — which is what
    the producer would fall back to if the proxy forgot to hand the store over.
    """
    from tabs.image_gallery.services import analysis_bridge

    real = analysis_bridge.engine_records

    def without_full_res_reference(*args, **kwargs):
        kwargs["tiled_source_store"] = None
        return real(*args, **kwargs)

    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_blocky_pair(size=(1200, 900), offset=8)).save(source)
    monkeypatch.setattr(
        analysis_bridge, "engine_records", without_full_res_reference
    )
    calls = _count_tiled(monkeypatch)

    _tiled_stages(item, source)

    assert calls.references == [(1024, 768)], (
        "a proxy-sized reference must be visible as such, or the gate above "
        "could pass for the wrong reason"
    )


def test_flag_on_full_res_fails_open_to_the_proxy_catalog(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """No full-res store ⇒ no tiled records: the entry stays the proxy catalog.

    The W14 store hand-over must not turn a decode failure into a missing stage:
    both the engine and the catalog call fall back to the same proxy catalog, so
    ``artifacts`` is exactly the catalog over the bounded proxy.
    """
    from engine.store.tiled_pixel_store import TiledPixelStore

    from tabs.image_gallery.services.proxy import proxy_for

    item = tmp_path / "blocky.png"
    _blocky_pair().save(item)
    source = tmp_path / "source.png"
    _source_variant(_gradient(96)).save(source)
    clear_proxy_cache()
    proxy = proxy_for(item)
    src_proxy = proxy_for(source)
    expected = artifacts.analyze_images(proxy.image, src_proxy.image)

    def _boom(cls, *args, **kwargs):  # pragma: no cover - exercised by injection
        raise OSError("synthetic full-res decode failure")

    monkeypatch.setattr(TiledPixelStore, "from_path", classmethod(_boom))
    entry = _tiled_stages(item, source)

    assert entry["artifacts"] == expected
    assert "analysis" in entry


def test_the_record_bridge_lives_in_analysis_bridge_not_the_proxy():
    """W14: the proxy imports the bridge; it does not own (or re-export) it."""
    from tabs.image_gallery.services import analysis_bridge, proxy

    moved = (
        "LEGACY_RAW_KEYS",
        "CAMERA_AXES",
        "FIDELITY_AXES",
        "ARTIFACT_AXES",
        "raw_dict",
        "artifact_dict",
        "upscale_factor",
        "records_by_axis",
        "unusable_axes",
        "stage_dicts_from_records",
        "engine_records",
    )
    for name in moved:
        assert hasattr(analysis_bridge, name), name
        assert name in analysis_bridge.__all__, name
        assert not hasattr(proxy, name), (
            f"{name} moved to analysis_bridge; services.proxy must not keep a "
            "second home (or a re-export) for the record glue"
        )


def test_same_file_pair_keeps_the_identity_fidelity(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """A same-file pair writes identity scores — definitional, not a measurement.

    ``_legacy_oracle`` returns the same dict, so this also pins that the identity
    shortcut survived the fallback deletion: it calls no detector, so it is not
    a legacy branch.
    """
    item, _source = _write_pair(tmp_path)
    calls = _seam_calls(monkeypatch)

    entry = _run_stages(item, item)

    assert entry["fidelity"] == {
        "ssim": 1.0,
        "hf_ratio": 0.0,
        "delta_e": 0.0,
        "upscale_factor": 1,
    }
    assert entry["fidelity"] == _legacy_oracle(item, item)["fidelity"]
    assert calls.legacy["fidelity"] == 0 and calls.total["fidelity"] == 0, (
        "identity scores are arithmetic, not a detector call"
    )

