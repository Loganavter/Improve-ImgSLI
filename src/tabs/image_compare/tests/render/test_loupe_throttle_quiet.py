"""Loupe trace quiet: throttled [ic-loupe] lines, truthful FrameContext records.

Regression for queue task-render-core-p3-residency-2026-09-13: the 8 M1
silent decisions (3 ``scene_update`` early returns, magnifier texture
choice, slot dedup, coord dedup, dropped non-resident slices — mag-gate
already records since P1A) now record into the P1A ``FrameContext`` under
``IMGSLI_IC_LOUPE_DEBUG``/``[ic-loupe]``. Modeled on
``test_keepwarm_idle_quiet.py``: eight identical frames must produce
bounded log lines (``<=1`` per throttle stream) while every hit still
appends its per-frame record; a changed decision signature must emit
again (guard against over-suppression); flag off must be a total no-op.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import tabs.image_compare.canvas.loupe_trace as loupe_mod
from tabs.image_compare.canvas.frame_context import FrameContext
from tabs.image_compare.canvas.loupe_trace import (
    reset_loupe_trace_state,
    trace_loupe,
)


@pytest.fixture
def loupe_env(monkeypatch):
    """Flag on + counted log lines + isolated throttle state."""
    monkeypatch.setenv("IMGSLI_IC_LOUPE_DEBUG", "1")
    reset_loupe_trace_state()
    lines: list = []
    _orig = loupe_mod.ic_loupe_debug
    monkeypatch.setattr(
        loupe_mod, "ic_loupe_debug", lambda msg, *a, **kw: lines.append((msg, a))
    )
    try:
        yield lines
    finally:
        reset_loupe_trace_state()
    assert _orig is not None  # keep linters honest about the wrapper above


def _std_ctx():
    return FrameContext()


def test_identical_frames_produce_bounded_loupe_lines(loupe_env):
    """8 identical hits per throttle mode: <=1 log line each, 8 records each."""
    lines = loupe_env
    for mode, kwargs in (
        ("sig", {}),
        ("time", {"throttle": "time"}),
        ("once", {"throttle": "once", "key": ("once-stream",)}),
    ):
        ctx = _std_ctx()
        for _ in range(8):
            trace_loupe(
                ctx,
                f"loupe.test_{mode}",
                "skipped",
                f"test {mode} identical reason",
                ids=("tile",),
                **kwargs,
            )
        assert len(ctx) == 8  # records are per-frame truth, never throttled
    # one line per stream (sig / time / once), not one per hit
    assert len(lines) <= 3


def test_changed_signature_emits_again(loupe_env):
    """Guard against over-suppression: a new decision sig logs again."""
    lines = loupe_env
    ctx = _std_ctx()
    for _ in range(8):
        trace_loupe(ctx, "loupe.test_sig", "skipped", "reason-a")
    assert len(lines) == 1
    trace_loupe(ctx, "loupe.test_sig", "skipped", "reason-b")
    assert len(lines) == 2
    assert len(ctx) == 9


def test_time_throttle_zero_interval_never_suppresses(loupe_env):
    """interval_s=0: every hit logs (mouse flow stays live when asked)."""
    lines = loupe_env
    ctx = _std_ctx()
    for _ in range(8):
        trace_loupe(
            ctx, "loupe.test_time", "skipped", "reason", throttle="time", interval_s=0
        )
    assert len(lines) == 8


def test_flag_off_is_total_noop(monkeypatch):
    """Flag off: no record, no log line, None returned."""
    monkeypatch.delenv("IMGSLI_IC_LOUPE_DEBUG", raising=False)
    reset_loupe_trace_state()
    lines: list = []
    monkeypatch.setattr(
        loupe_mod, "ic_loupe_debug", lambda msg, *a, **kw: lines.append((msg, a))
    )
    try:
        ctx = _std_ctx()
        assert trace_loupe(ctx, "loupe.test_off", "skipped", "reason") is None
        assert len(ctx) == 0
        assert lines == []
    finally:
        reset_loupe_trace_state()


# ---------------------------------------------------------------------------
# request_level: resident-or-pending-with-reason (+ interest rect)
# ---------------------------------------------------------------------------


def _make_2x2_service():
    from shared.rendering.tile_texture_service import TileTextureService

    service = TileTextureService(max_tile_extent=1024)
    service.register_source("img1", (2048, 2048))  # 2x2 grid
    return service


def test_request_level_all_resident():
    service = _make_2x2_service()
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("img1", index, byte_size=100, content_size=(1024, 1024))
    level, status, reason = service.request_level("img1", (0, 0, 2048, 2048))
    assert (level, status) == (0, "resident")
    assert reason == "all-4-tiles-resident"


def test_request_level_partial_pending_with_reason():
    service = _make_2x2_service()
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(1024, 1024))
    level, status, reason = service.request_level("img1", (0, 0, 2048, 2048))
    assert (level, status) == (0, "pending")
    assert reason == "3-of-4-tiles-missing"


def test_request_level_unknown_source_and_level():
    from shared.rendering.lod import LevelKey

    service = _make_2x2_service()
    assert service.request_level("nope", (0, 0, 64, 64))[1:] == (
        "pending",
        "source-unknown",
    )
    # level requested but never registered under LevelKey(sid, k)
    level, status, reason = service.request_level(
        "img1", (0, 0, 2048, 2048), dest_scale=0.25, level_count=3
    )
    assert level == 2
    assert (status, reason) == ("pending", "level-not-registered")
    # ...and resident once the level grid exists with all tiles uploaded
    service.register_source(LevelKey("img1", 2), (512, 512))
    for index in ((0, 0),):
        service.mark_resident(
            LevelKey("img1", 2), index, byte_size=10, content_size=(512, 512)
        )
    assert service.request_level(
        "img1", (0, 0, 2048, 2048), dest_scale=0.25, level_count=3
    )[1] == "resident"


def test_interest_rect_roundtrip():
    service = _make_2x2_service()
    assert service.interest_rect_for("img1") is None
    service.register_interest_rect("img1", (0, 0, 1024, 1024))
    assert service.interest_rect_for("img1") == (0, 0, 1024, 1024)
    service.register_interest_rect("img1", None)
    assert service.interest_rect_for("img1") is None


# ---------------------------------------------------------------------------
# dropped slices carry the request_level reason (P3b lens wiring)
# ---------------------------------------------------------------------------


def test_dropped_slice_records_carry_service_reason(loupe_env):
    """No resident tiles: slices drop, interest registered, reason recorded."""
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    lines = loupe_env
    service = _make_2x2_service()  # nothing marked resident
    renderer = SimpleNamespace(tile_service=service)
    ctx = _std_ctx()
    resolved = mag_mod._source_slices(
        renderer, "img1", (0.0, 0.0, 0.5, 0.5), frame_context=ctx
    )
    assert resolved == []
    # lens registered its interest rect in source-image pixels
    assert service.interest_rect_for("img1") == (0, 0, 1024, 1024)
    # every drop recorded with the service's pending reason, not silently
    drops = [d for d in ctx if d.pass_name == "loupe.mag_dropped_slice"]
    assert drops
    assert all("request_level=" in d.reason for d in drops)
    assert all(d.verdict == "skipped" for d in drops)
    # ...but the log stays bounded: one line per distinct (source, tile)
    assert len(lines) <= len(drops)
    # identical second frame: more records, no new lines
    before = len(lines)
    mag_mod._source_slices(renderer, "img1", (0.0, 0.0, 0.5, 0.5), frame_context=ctx)
    assert len(lines) == before


def test_resident_slices_stay_silent(loupe_env):
    """All resident: slices resolve, no drop records, interest still set."""
    from tabs.image_compare.canvas.features.magnifier.render import (
        magnifier_pass as mag_mod,
    )

    lines = loupe_env
    service = _make_2x2_service()
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("img1", index, byte_size=100, content_size=(1024, 1024))
    renderer = SimpleNamespace(tile_service=service)
    ctx = _std_ctx()
    resolved = mag_mod._source_slices(
        renderer, "img1", (0.0, 0.0, 0.5, 0.5), frame_context=ctx
    )
    assert resolved  # happy path unchanged: slices flow through
    assert service.interest_rect_for("img1") == (0, 0, 1024, 1024)
    assert [d for d in ctx if d.pass_name == "loupe.mag_dropped_slice"] == []
    assert lines == []
