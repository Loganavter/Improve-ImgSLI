"""Loupe no-holes: hold checks the same per-slice condition the frame draws.

Regression for the 2026-09-16 loupe repro (two 5760x4320 images): the trace
showed ``mag_texture_choice use_source=False`` (hold, stored) at T+0, then
``use_source=True`` (swap) at T+1.5s, and in the SAME frame 24x
``mag_dropped_slice`` with ``24-of-30-tiles-missing`` and zero
``mag_fallback_slice`` lines -- the level gate released while 24/30
per-slice ``slot_for`` lookups missed.

Reading verdict (see module docstring of the fix): the stated
level-vs-slot two-definitions hypothesis is REFUTED at the service layer
(``upload_tile_to_array`` -> ``mark_resident`` sets the ``_resident`` set
and the slot allocator together, synchronously; evict/reset/rekey free
both together -- so ``request_level == resident`` structurally implies
every ``slot_for`` hit for the same key+rect). The true chain is an
ungated draw key: the level gate (``_lens_residency_hold``) only checks the
two source keys, but ``build_tile_records`` in diff-lens mode
(``source_mode == 2``, ``diff_mode == 0``) samples ``diff_key`` -- which
has no fallback entry either -- so the swap frame draws diff holes.

The fix makes first-frame holes impossible by construction: ``prepare``
computes the frame's slice list first (pure geometry,
``_frame_draw_tile_indices``) and holds (samples stored) until EVERY slice
the frame would draw is GPU-resident (``_frame_slices_residency_hold``) --
the hold condition and the draw condition are the same check. These tests
pin that property at the gate level (a full ``MagnifierPass.prepare``
harness needs QRhi fakes; the gates plus ``_source_slices`` are exactly
the decision chain ``prepare`` runs):

1. diff-lens mode with lagging diff uploads (the observed shape: sources
   resident so the level gate releases, 24/30 diff slots pending) -- the
   slice gate holds, the draw drops instead of swapping.
2. all-resident -- the slice gate releases and the draw resolves every
   slice (atomic swap, full records, no drops, no fallback).
3. the hypothesized world itself (level resident, slots pending on the
   SAME key via a lagging stub service) -- the slice gate still holds, so
   the structural property survives even if the service ever splits the
   two definitions.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from engine.cache.tile_texture_service import TileTextureService
from engine.frame.context import FrameContext


@pytest.fixture(autouse=True)
def _loupe_debug_on(monkeypatch):
    """Loupe records append only with the debug flag on (see loupe_trace)."""
    from tabs.image_compare.canvas.loupe_trace import reset_loupe_trace_state

    monkeypatch.setenv("IMGSLI_IC_LOUPE_DEBUG", "1")
    reset_loupe_trace_state()
    yield
    reset_loupe_trace_state()


# The 2026-09-16 repro shape: 5760x4320 at 1024px extent -> 6 cols x 5 rows
# = 30 tiles; 6 uploaded, 24 missing.
_W, _H = 5760, 4320
_FULL_UV = (0.0, 0.0, 1.0, 1.0)
_RESIDENT_6 = ((0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (3, 3))


def _service_30_tiles():
    service = TileTextureService(max_tile_extent=1024)
    grid = service.register_source("src1", (_W, _H))
    assert (grid.rows, grid.columns) == (5, 6)
    service.register_source("src2", (_W, _H))
    service.register_source("diff1", (_W, _H))
    service.register_source("stored1", (512, 512))
    service.register_source("stored2", (512, 512))
    service.mark_resident("stored1", (0, 0), byte_size=100, content_size=(512, 512))
    service.mark_resident("stored2", (0, 0), byte_size=100, content_size=(512, 512))
    return service


def _overlay(*, source=0, uv=_FULL_UV):
    return SimpleNamespace(
        gpu_active=True,
        gpu_diff_mode=0,
        quads=[(0, 0, 100, 100, 50, 50, 40)],
        gpu_slots=[{"uv_rect": uv, "uv_rect2": uv, "source": source}],
    )


def _drops(ctx):
    return [d for d in ctx if d.pass_name == "loupe.mag_dropped_slice"]


def _fallbacks(ctx):
    return [d for d in ctx if d.pass_name == "loupe.mag_fallback_slice"]


# ---------------------------------------------------------------------------
# (1) diff-lens mode: level gate releases, slice gate holds (observed shape)
# ---------------------------------------------------------------------------


def test_diff_mode_slice_gate_holds_while_diff_uploads_lag():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _service_30_tiles()
    for index in _RESIDENT_6:
        service.mark_resident("diff1", index, byte_size=100)
    for key in ("src1", "src2"):
        for row in range(5):
            for col in range(6):
                service.mark_resident(key, (row, col), byte_size=100)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay(source=2)  # diff-lens mode

    # sources fully resident: the level gate releases (the old hole).
    assert (
        mag_mod._lens_residency_hold(renderer, ("src1", "src2"), overlay, ctx)
        is None
    )
    # ...but the frame would draw 30 diff slices, 24 without a GPU slot.
    indices = mag_mod._frame_draw_tile_indices(
        renderer, overlay, "src1", "src2", "diff1"
    )
    assert indices is not None
    assert len(indices) == 30
    assert all(key == "diff1" for key, _ in indices)
    hold = mag_mod._frame_slices_residency_hold(renderer, indices, ctx)
    assert hold is not None
    assert "24-of-30-slices-missing" in hold
    # the draw, ungated, would resolve only the 6 resident slices and drop
    # the other 24 with no fallback (diff has no stored entry) -- the
    # observed trace shape (24x mag_dropped_slice, zero mag_fallback_slice).
    draw_ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "diff1", _FULL_UV, frame_context=draw_ctx, fallback_key=None
    )
    assert len(resolved) == 6
    assert len(_drops(draw_ctx)) == 24
    assert _fallbacks(draw_ctx) == []


def test_diff_mode_all_resident_swaps_atomically_with_full_records():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _service_30_tiles()
    for key in ("src1", "src2", "diff1"):
        for row in range(5):
            for col in range(6):
                service.mark_resident(key, (row, col), byte_size=100)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay(source=2)

    assert (
        mag_mod._lens_residency_hold(renderer, ("src1", "src2"), overlay, ctx)
        is None
    )
    indices = mag_mod._frame_draw_tile_indices(
        renderer, overlay, "src1", "src2", "diff1"
    )
    assert mag_mod._frame_slices_residency_hold(renderer, indices, ctx) is None
    # atomic swap: every slice resolves, nothing drops, no fallback needed.
    draw_ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "diff1", _FULL_UV, frame_context=draw_ctx, fallback_key=None
    )
    assert len(resolved) == 30
    assert _drops(draw_ctx) == []
    assert _fallbacks(draw_ctx) == []


# ---------------------------------------------------------------------------
# (2) the hypothesized world: level resident, slots pending on one key
# ---------------------------------------------------------------------------


class _LaggingUploadService:
    """Wraps a real service with GPU upload completion lagging behind level
    bookkeeping: ``request_level`` answers resident while ``slot_for`` still
    misses the lagging tiles (the stated two-definitions hypothesis, made
    concrete so the gate must survive it). ``complete_uploads`` ends the
    lag. Everything else delegates to the wrapped service."""

    def __init__(self, inner, lagging):
        self._inner = inner
        self._lagging = set(lagging)

    def complete_uploads(self):
        self._lagging.clear()

    def request_level(self, source_id, rect=None, quality="high"):
        return (0, "resident", "all-30-tiles-resident")

    def slot_for(self, source_id, index):
        if (source_id, index) in self._lagging:
            return None
        return self._inner.slot_for(source_id, index)

    def __getattr__(self, name):
        return getattr(self.__dict__["_inner"], name)


def test_level_resident_slots_pending_still_holds():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    inner = TileTextureService(max_tile_extent=1024)
    inner.register_source("src1", (_W, _H))
    inner.register_source("src2", (_W, _H))
    inner.register_source("stored1", (512, 512))
    for row in range(5):
        for col in range(6):
            inner.mark_resident("src1", (row, col), byte_size=100)
            inner.mark_resident("src2", (row, col), byte_size=100)
    inner.mark_resident("stored1", (0, 0), byte_size=100, content_size=(512, 512))
    lagging = {
        ("src1", (row, col))
        for row in range(5)
        for col in range(6)
        if (row, col) not in set(_RESIDENT_6)
    }
    assert len(lagging) == 24
    service = _LaggingUploadService(inner, lagging)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay(source=0)

    # level says resident: the old gate releases...
    assert (
        mag_mod._lens_residency_hold(renderer, ("src1", "src2"), overlay, ctx)
        is None
    )
    # ...but the frame would draw 30 src1 slices with 24 slots pending:
    # hold (sample stored), never a partial grid.
    indices = mag_mod._frame_draw_tile_indices(
        renderer, overlay, "src1", "src2", "placeholder"
    )
    assert indices is not None
    assert len(indices) == 30
    hold = mag_mod._frame_slices_residency_hold(renderer, indices, ctx)
    assert hold is not None
    assert "24-of-30-slices-missing" in hold
    # held frames sample stored (already resident): full, no drops.
    draw_ctx = FrameContext()
    stored = mag_mod._source_slices(
        renderer, "stored1", _FULL_UV, frame_context=draw_ctx, fallback_key=None
    )
    assert len(stored) == 1
    assert _drops(draw_ctx) == []

    # uploads complete: atomic swap with full records, zero drops.
    service.complete_uploads()
    assert mag_mod._frame_slices_residency_hold(renderer, indices, ctx) is None
    swap_ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "src1", _FULL_UV, frame_context=swap_ctx, fallback_key="stored1"
    )
    assert len(resolved) == 30
    assert _drops(swap_ctx) == []
    assert _fallbacks(swap_ctx) == []


# ---------------------------------------------------------------------------
# (3) single-source modes gate exactly what they draw; fakes never hold
#
# H3 single-source repro (image-2 lens, the branch (1) never exercised):
# level-releases + 24/30 src2 slots pending + the OBSERVED single-source
# fallback state (stored2 resident, so the ungated draw would blur, not
# hole) -- the slice gate must still HOLD (first frame is an atomic swap,
# not fallback blur; fallback is for post-hold races only), then swap
# atomically with full records and ZERO fallback once all-resident.
# PASSES against the H1 gate (it already mirrors the source_mode==1
# branch) -- production untouched; this pins the mirror.
# ---------------------------------------------------------------------------


def test_single_source_image2_lagging_holds_then_swaps_atomically():
    """H3 single-source repro: image-2 lens, level releases, 24/30 pending.

    Same lagging-upload world as (2) but through the ``source_mode == 1``
    branch (draws ``tex_key_2`` with the stored2 fallback resident -- the
    observed single-source fallback state). The ungated draw would resolve
    every slice (6 source + 24 fallback blur, zero drops); the slice gate
    must still HOLD so the first frame is an atomic swap, not blur. After
    uploads complete the swap is full records with zero fallback needed.
    """
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    inner = _service_30_tiles()
    for row in range(5):
        for col in range(6):
            inner.mark_resident("src1", (row, col), byte_size=100)
            inner.mark_resident("src2", (row, col), byte_size=100)
    lagging = {
        ("src2", (row, col))
        for row in range(5)
        for col in range(6)
        if (row, col) not in set(_RESIDENT_6)
    }
    assert len(lagging) == 24
    service = _LaggingUploadService(inner, lagging)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay(source=1)  # image-2 lens: single key tex_key_2

    # level says resident: the old gate releases...
    assert (
        mag_mod._lens_residency_hold(renderer, ("src1", "src2"), overlay, ctx)
        is None
    )
    # ...but the frame would draw 30 src2 slices with 24 slots pending:
    # hold (sample stored), never a partial grid.
    indices = mag_mod._frame_draw_tile_indices(
        renderer, overlay, "src1", "src2", "placeholder"
    )
    assert indices is not None
    assert len(indices) == 30
    assert all(key == "src2" for key, _ in indices)
    hold = mag_mod._frame_slices_residency_hold(renderer, indices, ctx)
    assert hold is not None
    assert "24-of-30-slices-missing" in hold
    # the ungated draw would NOT hole here (stored2 covers: blur, 24
    # fallback records, zero drops) -- yet the gate still holds: first
    # frame swaps atomically, fallback stays for post-hold races only.
    blur_ctx = FrameContext()
    blurred = mag_mod._source_slices(
        renderer, "src2", _FULL_UV, frame_context=blur_ctx, fallback_key="stored2"
    )
    assert len(blurred) == 30
    assert _drops(blur_ctx) == []
    assert len(_fallbacks(blur_ctx)) == 24
    # held frames sample stored (already resident): full, no drops.
    draw_ctx = FrameContext()
    stored = mag_mod._source_slices(
        renderer, "stored2", _FULL_UV, frame_context=draw_ctx, fallback_key=None
    )
    assert len(stored) == 1
    assert _drops(draw_ctx) == []

    # uploads complete: atomic swap with full records, zero fallback needed.
    service.complete_uploads()
    assert mag_mod._frame_slices_residency_hold(renderer, indices, ctx) is None
    swap_ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "src2", _FULL_UV, frame_context=swap_ctx, fallback_key="stored2"
    )
    assert len(resolved) == 30
    assert _drops(swap_ctx) == []
    assert _fallbacks(swap_ctx) == []


def test_single_source_mode_gates_only_its_own_key():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _service_30_tiles()
    for row in range(5):
        for col in range(6):
            service.mark_resident("src2", (row, col), byte_size=100)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    overlay = _overlay(source=1)  # image2 lens

    indices = mag_mod._frame_draw_tile_indices(
        renderer, overlay, "src1", "src2", "diff1"
    )
    assert indices is not None
    assert len(indices) == 30
    assert all(key == "src2" for key, _ in indices)
    assert mag_mod._frame_slices_residency_hold(renderer, indices, ctx) is None


def test_no_tile_service_never_holds():
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    overlay = _overlay(source=2)
    renderer = SimpleNamespace(tile_service=None)
    assert (
        mag_mod._frame_draw_tile_indices(
            renderer, overlay, "src1", "src2", "diff1"
        )
        is None
    )
    assert (
        mag_mod._frame_slices_residency_hold(renderer, None, FrameContext())
        is None
    )


# ---------------------------------------------------------------------------
# (4) H3: no-fallback WHY rides on the drop reason, not silent (fallback_key
# None vs grid unknown vs not resident -- one event, one line)
# ---------------------------------------------------------------------------


def test_no_fallback_key_is_logged_not_silent():
    """The observed silence, pinned: the diff key has no fallback entry, so
    the 24 drops came with zero fallback lines AND zero explanation. Now
    every drop records its no-fallback cause (``nofallback=no_fallback_key``)
    with per-tile ids -- the same single aggregated log line carries it."""
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    service = _service_30_tiles()
    for index in _RESIDENT_6:
        service.mark_resident("diff1", index, byte_size=100)
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    resolved = mag_mod._source_slices(
        renderer, "diff1", _FULL_UV, frame_context=ctx, fallback_key=None
    )
    assert len(resolved) == 6
    drops = _drops(ctx)
    assert len(drops) == 24
    assert all("nofallback=no_fallback_key" in d.reason for d in drops)
    assert all(d.verdict == "skipped" for d in drops)
    assert any((4, 0) in d.ids for d in drops)  # tile identity preserved


def test_fallback_miss_logs_why():
    """Fallback attempted but covering nothing: the drop reason says which --
    stored grid not resident vs fallback key never registered."""
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )
    from engine.cache.tile_texture_service import TileTextureService

    # stored registered but never uploaded: slot miss per slice.
    service = TileTextureService(max_tile_extent=1024)
    service.register_source("src", (2048, 2048))  # 2x2, never uploaded
    service.register_source("stored", (512, 512))
    renderer = SimpleNamespace(tile_service=service)
    ctx = FrameContext()
    assert (
        mag_mod._source_slices(
            renderer, "src", _FULL_UV, frame_context=ctx, fallback_key="stored"
        )
        == []
    )
    drops = _drops(ctx)
    assert len(drops) == 4
    assert all("nofallback=fallback_slot_not_resident" in d.reason for d in drops)

    # fallback key never registered: grid unknown, no drops change.
    ctx2 = FrameContext()
    assert (
        mag_mod._source_slices(
            renderer, "src", _FULL_UV, frame_context=ctx2, fallback_key="nope"
        )
        == []
    )
    drops2 = _drops(ctx2)
    assert len(drops2) == 4
    assert all("nofallback=fallback_grid_unknown" in d.reason for d in drops2)


# ---------------------------------------------------------------------------
# (5) H3 behavior-identity self-check: trace points change no returns
# ---------------------------------------------------------------------------


def test_source_slices_returns_identical_with_trace_on_and_off(monkeypatch):
    """Same service state, flag on vs off: identical resolved slices.

    The H3 additions are trace records only -- the draw result (resolved
    list, drops implied) must not depend on ``IMGSLI_IC_LOUPE_DEBUG``.
    """
    from tabs.image_compare.canvas.loupe_trace import reset_loupe_trace_state
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    def _draw():
        service = _service_30_tiles()
        for index in _RESIDENT_6:
            service.mark_resident("diff1", index, byte_size=100)
        renderer = SimpleNamespace(tile_service=service)
        ctx = FrameContext()
        resolved = mag_mod._source_slices(
            renderer, "diff1", _FULL_UV, frame_context=ctx, fallback_key=None
        )
        fallback_resolved = mag_mod._source_slices(
            renderer, "src1", _FULL_UV, frame_context=ctx, fallback_key="stored1"
        )
        return resolved, fallback_resolved, ctx

    on_resolved, on_fallback, on_ctx = _draw()
    assert len(_drops(on_ctx)) == 24  # drop path exercised in both runs
    monkeypatch.delenv("IMGSLI_IC_LOUPE_DEBUG", raising=False)
    reset_loupe_trace_state()
    off_resolved, off_fallback, off_ctx = _draw()
    assert off_resolved == on_resolved
    assert off_fallback == on_fallback
    assert len(off_ctx) == 0  # flag off: total no-op, no records
