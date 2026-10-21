"""W7: the runner executes a resolved plan and never propagates a producer error.

``plan-gallery-analysis-engine-2026-10-20`` §P1/P3: the plan says what may run,
the runner says what happened. The properties pinned here are the ones a batch
depends on: records stay in plan order, every item gets an entry, a raising
producer degrades only its own axes (``status="error"`` + one journal entry),
a producer's gap passes through untouched, and an empty context mapping is a
no-op rather than an error.
"""

from __future__ import annotations

import pytest

from engine.analysis.contracts import (
    AnalysisPlan,
    AxisValue,
    ProducerSpec,
    RunJournal,
)
from engine.analysis.registry import ProducerRegistry, discover
from engine.analysis.resolver import Resolution, resolve_plan

from tabs.image_gallery.analysis import runner
from tabs.image_gallery.analysis.context_builder import build_context
from tabs.image_gallery.analysis.runner import run_plan

PRODUCERS = "tabs.image_gallery.analysis.producers"

CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance")
FIDELITY_AXES = (
    "ssim",
    "detail_gain",
    "color_accuracy",
    "clipping_delta",
    "halo_delta",
    "chroma_fringe_delta",
    # W13: the learned pair is measured by the fidelity producer.
    "lpips",
    "dists",
)
ARTIFACT_AXES = (
    "banding",
    "halo",
    "over_smoothing",
    "invented_texture",
    "blocking",
    "chroma_fringing",
    "noise_amplification",
)


def _gradient(size: int = 48):
    """A decoded gradient: every local detector can chew on it."""
    from PIL import Image

    image = Image.new("RGB", (size, size))
    pixels = image.load()
    span = max(2 * (size - 1), 1)
    for y in range(size):
        for x in range(size):
            value = int((x + y) * 255 / span)
            pixels[x, y] = (value, value, value)
    return image


def _resolution(*specs: ProducerSpec) -> Resolution:
    """A hand-built resolution (plan order = the spec order given)."""
    return Resolution(
        plan=AnalysisPlan(
            id="test-plan",
            generation=0,
            policy="local",
            runs=tuple(spec.id for spec in specs),
        ),
        runs=tuple(specs),
        gaps=(),
    )


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_happy_path_returns_one_entry_per_item_in_plan_order(
    monkeypatch: pytest.MonkeyPatch,
):
    # LPIPS/DISTS are part of the fidelity producer since W13; fake the learned
    # seam so the happy path stays deterministic whether or not torch/piq are
    # installed (the real backend is covered by test_quality_backend_required.py).
    from tabs.image_gallery.services import quality_models

    monkeypatch.setattr(
        quality_models,
        "pair_metrics",
        lambda item, source, *a, **kw: {"lpips": 0.2, "dists": 0.15},
    )
    registry = discover(PRODUCERS)
    resolution = resolve_plan(
        registry,
        policy="local",
        capabilities=frozenset({"images", "reference"}),
    )
    image = _gradient()
    contexts = {
        "b.png": build_context(
            "b.png", proxy_image=image, source_image=image.copy()
        ),
        "a.png": build_context(
            "a.png", proxy_image=image, source_image=image.copy()
        ),
    }

    records, journal = run_plan(resolution, contexts)

    assert tuple(records) == ("a.png", "b.png"), (
        "item order must not depend on the caller's mapping insertion order"
    )
    expected_axes = (
        *CAMERA_AXES,
        *FIDELITY_AXES,
        *ARTIFACT_AXES,
    )
    assert len(records["a.png"]) == len(expected_axes) == 20
    assert all(isinstance(record, AxisValue) for record in records["a.png"])
    # Plan order = the resolver's registry order (artifacts … camera … fidelity),
    # and the tuple order is that plan order, not the axis vocabulary order.
    assert tuple(record.axis for record in records["a.png"]) == tuple(
        record.axis
        for spec in resolution.runs
        for record in _records_for(records["a.png"], spec)
    )
    assert isinstance(journal, RunJournal)
    assert len(journal.entries) == 2 * len(resolution.runs)
    assert {entry.status for entry in journal.entries} == {"ok"}
    assert sum(entry.items for entry in journal.entries) == 2 * len(expected_axes)


def _records_for(records: tuple[AxisValue, ...], spec: ProducerSpec):
    axes = set(spec.provides)
    return [record for record in records if record.axis in axes]


def test_plan_order_wins_over_registry_order():
    registry = discover(PRODUCERS)
    fidelity = registry.get("fidelity_reference")
    camera = registry.get("camera_scalars")
    assert fidelity is not None and camera is not None
    resolution = _resolution(fidelity, camera)
    image = _gradient()
    ctx = build_context("item.png", proxy_image=image, source_image=image.copy())

    records, _journal = run_plan(resolution, {"item.png": ctx})

    assert tuple(record.axis for record in records["item.png"]) == (
        *FIDELITY_AXES,
        *CAMERA_AXES,
    )


def test_empty_context_mapping_is_a_no_op():
    resolution = resolve_plan(discover(PRODUCERS), policy="local")

    records, journal = run_plan(resolution, {})

    assert records == {}
    assert journal == RunJournal(entries=())


# ---------------------------------------------------------------------------
# degradation: a producer never takes the batch down
# ---------------------------------------------------------------------------


def test_a_raising_producer_becomes_error_records_and_one_journal_entry(
    monkeypatch: pytest.MonkeyPatch,
):
    spec = ProducerSpec(
        id="exploding",
        provides={"sharpness": "measured", "noise": "measured"},
        requires=frozenset({"images"}),
    )

    def explode(ctx):
        raise RuntimeError("detector crashed")

    monkeypatch.setattr(runner, "_run_for", lambda producer_id: explode)
    ctx = build_context("item.png", proxy_image=_gradient())

    records, journal = run_plan(_resolution(spec), {"item.png": ctx})

    assert len(records["item.png"]) == 2
    for record in records["item.png"]:
        assert record.producer == "exploding"
        assert record.status == "error"
        assert record.value is None
        assert record.reason == "RuntimeError: detector crashed"
    assert len(journal.entries) == 1
    entry = journal.entries[0]
    assert (entry.producer, entry.status) == ("exploding", "error")
    assert entry.reason == "RuntimeError: detector crashed"


def test_an_uninstalled_producer_degrades_to_error_records():
    """A stale plan naming a removed package must not raise either."""
    spec = ProducerSpec(
        id="not_installed_anywhere",
        provides={"sharpness": "measured"},
        requires=frozenset({"images"}),
    )
    ctx = build_context("item.png", proxy_image=_gradient())

    records, journal = run_plan(_resolution(spec), {"item.png": ctx})

    record = records["item.png"][0]
    assert record.status == "error"
    assert "not_installed_anywhere" in record.reason
    assert journal.entries[0].status == "error"


def test_a_producers_gap_passes_through_unchanged():
    registry = discover(PRODUCERS)
    camera = registry.get("camera_scalars")
    assert camera is not None
    # No proxy image: the producer answers every axis with an explicit gap.
    ctx = build_context("item.png")

    records, journal = run_plan(_resolution(camera), {"item.png": ctx})

    assert tuple(record.axis for record in records["item.png"]) == CAMERA_AXES
    for record in records["item.png"]:
        assert record.status == "gap"
        assert record.value is None
        assert record.reason, "a gap always explains itself"
    assert journal.entries[0].status == "gap"
    assert journal.entries[0].reason


def test_one_broken_producer_does_not_hide_a_working_one(
    monkeypatch: pytest.MonkeyPatch,
):
    registry = discover(PRODUCERS)
    camera = registry.get("camera_scalars")
    assert camera is not None
    broken = ProducerSpec(
        id="exploding",
        provides={"noise": "measured"},
        requires=frozenset({"images"}),
    )
    real_run_for = runner._run_for

    def run_for(producer_id: str):
        if producer_id == "exploding":
            def explode(ctx):
                raise ValueError("boom")
            return explode
        return real_run_for(producer_id)

    monkeypatch.setattr(runner, "_run_for", run_for)
    ctx = build_context("item.png", proxy_image=_gradient())

    records, journal = run_plan(_resolution(broken, camera), {"item.png": ctx})

    by_status = {record.status for record in records["item.png"]}
    assert "error" in by_status and "ok" in by_status
    assert tuple(entry.status for entry in journal.entries) == ("error", "ok")
