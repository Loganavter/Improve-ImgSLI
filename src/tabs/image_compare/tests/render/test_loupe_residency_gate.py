"""Loupe residency gate: stored-hold + low-res fallback + lens priority.

Regression for the 2026-09-14 loupe repro (tile holes on the first source
frame: 24-of-30-missing x24 identical log lines). The lens flipped to
``use_source`` on image-readiness, not residency, so the first source
frames sampled a half-uploaded grid. Fix, in order:

1. HOLD stored until ``request_level`` on the lens interest rect reports
   resident (atomic swap instead of progressive fill).
2. Sample missing slices from stored/low-res instead of dropping them
   (blur, not holes).
3. Lens interest first-class in ``select_upload_batch`` + real ``diff_key``
   in the magnifier residency call + coarsest LOD pinned against eviction.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.frame_context import FrameContext

import pytest


@pytest.fixture(autouse=True)
def _loupe_debug_on(monkeypatch):
    """Loupe records append only with the debug flag on (see loupe_trace)."""
    from tabs.image_compare.canvas.loupe_trace import reset_loupe_trace_state

    monkeypatch.setenv("IMGSLI_IC_LOUPE_DEBUG", "1")
    reset_loupe_trace_state()
    yield
    reset_loupe_trace_state()


def _make_service(**kwargs):
    return TileTextureService(max_tile_extent=1024, **kwargs)


def _overlay(*uv_rects):
    return SimpleNamespace(
        gpu_slots=[
            {"uv_rect": uv, "uv_rect2": uv} for uv in uv_rects
        ]
    )


# ---------------------------------------------------------------------------
# (1) stored-hold until the lens interest rect is resident
# ---------------------------------------------------------------------------


def test_hold_until_lens_interest_resident():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _make_service()
    service.register_source("src1", (2048, 2048))  # 2x2
    service.register_source("src2", (2048, 2048))  # 2x2
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay((0.0, 0.0, 1.0, 1.0))

    hold = mag_mod._lens_residency_hold(
        renderer, ("src1", "src2"), overlay, ctx
    )
    assert hold is not None
    assert "4-of-4-tiles-missing" in hold
    # lens registered its interest rect in source-image pixels
    assert service.interest_rect_for("src1") == (0, 0, 2048, 2048)

    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("src1", index, byte_size=100)
        service.mark_resident("src2", index, byte_size=100)
    assert (
        mag_mod._lens_residency_hold(renderer, ("src1", "src2"), overlay, ctx)
        is None
    )


def test_hold_partial_interest_stays_held():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _make_service()
    service.register_source("src1", (2048, 2048))
    service.register_source("src2", (2048, 2048))
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay((0.0, 0.0, 1.0, 1.0))

    # src1 fully resident, src2 untouched: still held (atomic swap, not
    # progressive -- one pending side holds both).
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("src1", index, byte_size=100)
    hold = mag_mod._lens_residency_hold(
        renderer, ("src1", "src2"), overlay, ctx
    )
    assert hold is not None
    assert "src2" in hold


def test_hold_never_blocks_without_tile_service():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    # fakes/tests without a renderer keep the old behavior exactly
    assert (
        mag_mod._lens_residency_hold(
            SimpleNamespace(tile_service=None),
            ("src1", "src2"),
            _overlay((0.0, 0.0, 1.0, 1.0)),
            FrameContext(),
        )
        is None
    )
    assert (
        mag_mod._lens_residency_hold(
            None, ("src1", "src2"), _overlay((0.0, 0.0, 1.0, 1.0)), None
        )
        is None
    )


# ---------------------------------------------------------------------------
# (2) low-res fallback instead of holes
# ---------------------------------------------------------------------------


def _fallback_setup(*, stored_resident=True):
    service = _make_service()
    service.register_source("src", (2048, 2048))  # 2x2, never uploaded
    service.register_source("stored", (512, 512))  # 1x1 low-res
    if stored_resident:
        service.mark_resident(
            "stored", (0, 0), byte_size=100, content_size=(512, 512)
        )
    return service


def test_missing_slices_sample_stored_fallback():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _fallback_setup()
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "src", (0.0, 0.0, 1.0, 1.0),
        frame_context=ctx, fallback_key="stored",
    )
    # no holes: all four source tiles covered by a stored sample each
    assert len(resolved) == 4
    stored_layer = service.slot_for("stored", (0, 0))[1]
    assert all(sl["layer"] == stored_layer for sl in resolved)
    assert all(sl["fallback_for"] is not None for sl in resolved)
    # fallback recorded, nothing dropped
    assert [d for d in ctx if d.pass_name == "loupe.mag_dropped_slice"] == []
    assert [d for d in ctx if d.pass_name == "loupe.mag_fallback_slice"]


def test_no_fallback_anywhere_still_drops_with_tile_index():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _fallback_setup(stored_resident=False)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "src", (0.0, 0.0, 1.0, 1.0),
        frame_context=ctx, fallback_key="stored",
    )
    assert resolved == []
    drops = [d for d in ctx if d.pass_name == "loupe.mag_dropped_slice"]
    assert drops
    # the drop reason names its tile index (repro-grade diagnostics)
    assert any("tile=(0, 1)" in d.reason for d in drops)
    assert all("request_level=" in d.reason for d in drops)


def test_no_fallback_key_keeps_old_drop_path():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _fallback_setup()
    renderer = SimpleNamespace(tile_service=service)
    resolved = mag_mod._source_slices(
        renderer, "src", (0.0, 0.0, 1.0, 1.0), frame_context=FrameContext()
    )
    assert resolved == []


# ---------------------------------------------------------------------------
# (3a) lens-interest-first upload priority
# ---------------------------------------------------------------------------


def test_interest_tiles_upload_before_margin():
    service = TileTextureService(max_tile_extent=512)
    service.register_source("big", (2048, 2048))  # 4x4
    service.register_interest_rect("big", (0, 0, 512, 512))  # tile (0,0)
    missing = {(r, c) for r in range(4) for c in range(4)}
    batch = service.select_upload_batch(
        "big", missing, (0, 0, 2048, 2048), budget=2
    )
    assert batch[0] == (0, 0)


def test_explicit_interest_rect_overrides_registry():
    service = TileTextureService(max_tile_extent=512)
    service.register_source("big", (2048, 2048))  # 4x4
    service.register_interest_rect("big", (0, 0, 512, 512))
    missing = {(r, c) for r in range(4) for c in range(4)}
    batch = service.select_upload_batch(
        "big",
        missing,
        (0, 0, 2048, 2048),
        budget=2,
        interest_rect=(1536, 1536, 2048, 2048),  # tile (3,3)
    )
    assert batch[0] == (3, 3)


def test_no_interest_keeps_visible_center_order():
    service = TileTextureService(max_tile_extent=512)
    service.register_source("big", (2048, 2048))  # 4x4, no interest
    missing = {(r, c) for r in range(4) for c in range(4)}
    batch = service.select_upload_batch(
        "big", missing, (0, 0, 2048, 2048), budget=2
    )
    # center-nearest first with (row, col) tie-break -- pre-gate behavior
    assert batch == [(1, 1), (1, 2)]


# ---------------------------------------------------------------------------
# (3b) coarsest LOD pinned against eviction
# ---------------------------------------------------------------------------


def test_pin_coarsest_level_survives_eviction():
    from shared.rendering.lod import LevelKey

    service = _make_service()
    service.register_source(LevelKey("s", 1), (1024, 1024))
    service.register_source(LevelKey("s", 2), (512, 512))  # coarsest
    service.mark_resident(LevelKey("s", 1), (0, 0), byte_size=400)
    service.mark_resident(LevelKey("s", 2), (0, 0), byte_size=400)

    assert service.pin_coarsest_level("s") == LevelKey("s", 2)
    assert service.is_pinned(LevelKey("s", 2))
    assert not service.is_pinned(LevelKey("s", 1))

    evicted = service.evict_over_budget({}, budget_bytes=0)
    assert (LevelKey("s", 2), (0, 0)) not in evicted
    assert (LevelKey("s", 1), (0, 0)) in evicted
    assert service.is_resident(LevelKey("s", 2), (0, 0))

    service.set_pinned(LevelKey("s", 2), False)
    evicted = service.evict_over_budget({}, budget_bytes=0)
    assert (LevelKey("s", 2), (0, 0)) in evicted


def test_pin_coarsest_level_no_pyramid_is_noop():
    service = _make_service()
    service.register_source("plain", (512, 512))
    assert service.pin_coarsest_level("plain") is None
    assert service.pin_coarsest_level("unknown") is None


# ---------------------------------------------------------------------------
# (3c) real diff_key in the magnifier residency call
# ---------------------------------------------------------------------------


class _FakeResidency:
    def __init__(self):
        self.calls: list = []

    def realize_tile_plan(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return False


def _mag_harness(*, diff_ready=True):
    service = _make_service()
    service.register_source("src1", (512, 512))
    service.register_source("src2", (512, 512))
    residency = _FakeResidency()
    renderer = SimpleNamespace(
        tile_service=service,
        resources=SimpleNamespace(residency=residency),
    )
    widget = SimpleNamespace(
        runtime_state=SimpleNamespace(), update=lambda: None
    )
    overlay = _overlay((0.0, 0.0, 0.5, 0.5))
    overlay.gpu_active = True
    ctx = SimpleNamespace(
        feature_overlay=overlay,
        source_texture_ids=("src1", "src2"),
        source_images_ready=True,
        diff_source_texture_id="diff1",
        diff_source_ready=diff_ready,
    )
    return renderer, widget, ctx, residency


def test_magnifier_residency_passes_real_diff_key():
    from tabs.image_compare.canvas.rhi_renderer.use_cases import (
        tile_residency as residency_mod,
    )

    renderer, widget, ctx, residency = _mag_harness(diff_ready=True)
    residency_mod.realize_magnifier_tiles(
        renderer,
        widget,
        ctx,
        ("stored1", "stored2"),
        None,
        None,
        None,
        None,
        {},
    )
    assert len(residency.calls) == 1
    _, kwargs = residency.calls[0]
    assert kwargs["diff_key"] == "diff1"
    assert kwargs["capture_uv_rect"] == (0.0, 0.0, 0.5, 0.5)


def test_magnifier_residency_no_diff_when_not_ready():
    from tabs.image_compare.canvas.rhi_renderer.use_cases import (
        tile_residency as residency_mod,
    )

    renderer, widget, ctx, residency = _mag_harness(diff_ready=False)
    residency_mod.realize_magnifier_tiles(
        renderer,
        widget,
        ctx,
        ("stored1", "stored2"),
        None,
        None,
        None,
        None,
        {},
    )
    assert len(residency.calls) == 1
    _, kwargs = residency.calls[0]
    assert kwargs["diff_key"] is None
