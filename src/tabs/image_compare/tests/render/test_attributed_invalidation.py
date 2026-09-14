"""P4 attributed invalidation bus: arms are answerable, idle stays quiet.

Proves the plan-render-core-consolidation Phase P4 bus:
N ``schedule_update`` arms produce N ``invalidate.*`` FrameContext records
(who + why), while steady healthy-idle keep-warm ticks produce zero frames
(``update()`` never fires) and each tick outcome is itself an attributed
skip record. Flag off → zero records (one env check per site).

Timer audit table (image_compare render path; P4 verdict per timer):

1. keep-warm QTimer 250 ms (``canvas/widget.py::_ensure_dnd_keepwarm``)
   → ATTRIBUTED: ``invalidate.keepwarm.armed`` once + every tick records
   ``invalidate.keepwarm.tick`` (fired with pending cause / skipped with
   stand-down reason). Healthy-idle skip path is byte-identical.
2. WASD movement QTimer 8 ms precise
   (``canvas/features/magnifier/input/keyboard_movement.py``)
   → ATTRIBUTED at lifecycle level: ``invalidate.keyboard_movement``
   on start + on every stop (stop()/converged/single-image). Per-tick
   records deliberately omitted (125 Hz); the pump stops on convergence
   so steady idle yields zero ticks by construction.
3. fps singleShot scheduler (created
   ``presenters/image_canvas/lifecycle.py``, armed
   ``background_parts/use_cases/schedule.py::schedule_update``)
   → ATTRIBUTED: ``invalidate.schedule.fps_timer`` on every arm AND on
   every already-armed dedup-ack, ``invalidate.schedule.interactive``
   on the immediate path, ``invalidate.schedule.background`` on the
   hidden-tab stale path. singleShot ⇒ one fire per start(): no arms in
   steady idle means zero ticks by construction.
4. DnD restack singleShot 120 ms (``canvas/widget.py``)
   → ATTRIBUTED: ``invalidate.dnd_restack`` on arm (one-shot, drag-scoped).
5. first-present settle singleShot(0) ×2 (``canvas/widget.py``
   showEvent + ``_settle_first_presents``) → ATTRIBUTED:
   ``invalidate.first_present.settle`` / ``.flush`` (bounded: present
   gate / show edge, never polling).
6. first-frame sampler 50 ms ×30 (``canvas/widget.py``) → KEPT WITH
   REASON: debug-flag-gated, bounded, never calls ``update()`` — no frame
   can come from here by construction, so no record.
7. PIL letterbox refresh singleShot 120 ms (``canvas/render_context.py``)
   → ATTRIBUTED: ``invalidate.pil_letterbox`` (dedup-flagged, one
   outstanding deferral at most).
8. glass settle singleShot(0) (``canvas/render_context.py``)
   → ATTRIBUTED: ``invalidate.glass_settle`` (single pending flag:
   bursts coalesce to one settle frame).
9. source preload singleShot(0) (``canvas/render_context.py``)
   → ATTRIBUTED: ``invalidate.source_preload`` (dedup-flagged, never a
   polling loop).
10. magnifier invalidation origins (``workers/diff_cache.py`` cached-diff
    ready, ``workers/result_handlers.py`` movement stopped) → ATTRIBUTED:
    ``invalidate.diff_cache`` / ``invalidate.interaction`` origin records;
    the fps-timer arm itself is recorded in (3).
11. slot/coords dedup early-returns (``feature_overlay_gpu.py``,
    ``canvas/interaction.py``) → ALREADY ATTRIBUTED by P3
    (``loupe.slot_dedup`` / ``loupe.coords_dedup``); untouched here.

Out of render-path scope (unchanged, no record): toolbar/flyout/
session-persistence/video-editor singleShots, preview-updater/playback/
recorder timers — none can arm a canvas frame.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def invalidate_on(monkeypatch):
    monkeypatch.setenv("IMGSLI_IC_INVALIDATE_DEBUG", "1")


@pytest.fixture
def invalidate_off(monkeypatch):
    monkeypatch.delenv("IMGSLI_IC_INVALIDATE_DEBUG", raising=False)


def _ctx_with_widget_ctx():
    from engine.frame.context import FrameContext

    return FrameContext()


def _schedule_presenter(ctx, *, interactive=False, visible=True):
    """Fake ImageCanvasPresenter sufficient for schedule_update()."""
    from PySide6.QtCore import QTimer as _QTimer

    widget = SimpleNamespace(
        isVisible=lambda: visible,
        _rhi_renderer=SimpleNamespace(frame_context=ctx),
    )
    presenter = SimpleNamespace(
        widget=widget,
        main_window_app=SimpleNamespace(),
        store=SimpleNamespace(
            viewport=SimpleNamespace(
                interaction_state=SimpleNamespace(
                    is_interactive_mode=interactive,
                ),
            ),
        ),
        _update_scheduler_timer=_QTimer(),
        _pending_interactive_mode=None,
        update_comparison_if_needed=lambda: False,
    )
    presenter._update_scheduler_timer.setSingleShot(True)
    presenter._update_scheduler_timer.setInterval(16)
    return presenter


def _invalidate_records(ctx):
    return [d for d in ctx if d.pass_name.startswith("invalidate.")]


def test_scheduler_arms_produce_attributed_records(qapp, invalidate_on):
    from tabs.image_compare.presenters.image_canvas.background_parts.use_cases import (
        schedule as sched_mod,
    )

    ctx = _ctx_with_widget_ctx()
    presenter = _schedule_presenter(ctx)
    assert not presenter._update_scheduler_timer.isActive()

    # N arms (timer stopped between calls) -> N attributed arm records.
    for _ in range(3):
        presenter._update_scheduler_timer.stop()
        sched_mod.schedule_update(presenter)
        assert presenter._update_scheduler_timer.isActive()

    arms = [
        d
        for d in _invalidate_records(ctx)
        if d.pass_name == "invalidate.schedule.fps_timer" and d.verdict == "ran"
    ]
    assert len(arms) == 3
    assert all("fps timer armed" in d.reason for d in arms)

    # Already-armed call -> attributed dedup-ack (skipped), no re-arm spam.
    before = len(_invalidate_records(ctx))
    sched_mod.schedule_update(presenter)
    after = _invalidate_records(ctx)
    assert len(after) == before + 1
    assert after[-1].pass_name == "invalidate.schedule.fps_timer"
    assert after[-1].verdict == "skipped"
    assert "already armed" in after[-1].reason


def test_scheduler_interactive_and_background_paths_attributed(
    qapp, invalidate_on
):
    from tabs.image_compare.presenters.image_canvas.background_parts.use_cases import (
        schedule as sched_mod,
    )

    ctx = _ctx_with_widget_ctx()
    presenter = _schedule_presenter(ctx, interactive=True)
    sched_mod.schedule_update(presenter)
    recs = _invalidate_records(ctx)
    assert len(recs) == 1
    assert recs[0].pass_name == "invalidate.schedule.interactive"
    assert "immediate update" in recs[0].reason
    assert not presenter._update_scheduler_timer.isActive()

    ctx2 = _ctx_with_widget_ctx()
    hidden = _schedule_presenter(ctx2, visible=False)
    sched_mod.schedule_update(hidden)
    recs2 = _invalidate_records(ctx2)
    assert len(recs2) == 1
    assert recs2[0].pass_name == "invalidate.schedule.background"
    assert recs2[0].verdict == "skipped"
    assert getattr(hidden.widget, "_render_stale", False) is True


def _healthy_keepwarm_fake(ctx):
    keys = ("img1", "img2")

    class Fake(QObject):
        def __init__(self):
            super().__init__()
            self.runtime_state = SimpleNamespace(
                _drag_overlay_visible=False,
                _tile_more_pending=False,
            )
            self._rhi_renderer = SimpleNamespace(
                _last_good_texture_keys=keys,
                _pending_dirty_layers={},
                _lod_committed_keys=keys,
                _content_swap_active=False,
                _fallback_more_pending_snapshot=False,
                frame_context=ctx,
            )
            self.updates = 0
            self._visible = True
            self._minimized = False

        def isVisible(self):  # noqa: N802
            return self._visible

        def window(self):
            return SimpleNamespace(isMinimized=lambda: self._minimized)

        def update(self):  # noqa: N802
            self.updates += 1

    return Fake()


def _keepwarm_timers(fake):
    return [t for t in fake.findChildren(QTimer) if t.interval() > 0]


def test_keepwarm_healthy_idle_produces_no_frames_but_attributed_skips(
    qapp, invalidate_on
):
    """Bounded keep-warm model: 8 healthy-idle ticks, 0 frames, 8+1 records."""
    from tabs.image_compare.canvas import widget as wmod

    ctx = _ctx_with_widget_ctx()
    fake = _healthy_keepwarm_fake(ctx)
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _keepwarm_timers(fake)
    assert len(timers) == 1
    for _ in range(8):
        timers[0].timeout.emit()
    # Steady healthy idle: no frame is ever produced...
    assert fake.updates == 0
    # ...while every tick outcome stays answerable: 1 arm + 8 idle skips.
    recs = _invalidate_records(ctx)
    arms = [d for d in recs if d.pass_name == "invalidate.keepwarm.armed"]
    skips = [
        d
        for d in recs
        if d.pass_name == "invalidate.keepwarm.tick" and d.verdict == "skipped"
    ]
    assert len(arms) == 1
    assert "interval_ms=" in arms[0].reason
    assert len(skips) == 8
    assert all("healthy idle" in d.reason for d in skips)


def test_keepwarm_busy_still_primes_with_firing_records(qapp, invalidate_on):
    """Guard against over-suppression: pending work still ticks (attributed)."""
    from tabs.image_compare.canvas import widget as wmod

    ctx = _ctx_with_widget_ctx()
    fake = _healthy_keepwarm_fake(ctx)
    fake.runtime_state._tile_more_pending = True
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _keepwarm_timers(fake)
    assert len(timers) == 1
    for _ in range(3):
        timers[0].timeout.emit()
    assert fake.updates == 3
    fires = [
        d
        for d in _invalidate_records(ctx)
        if d.pass_name == "invalidate.keepwarm.tick" and d.verdict == "ran"
    ]
    assert len(fires) == 3
    assert all("tile_more_pending" in d.reason for d in fires)


def test_flag_off_costs_no_records(qapp, invalidate_off):
    """Flag off: identical behavior, zero attribution records."""
    from tabs.image_compare.canvas import widget as wmod
    from tabs.image_compare.presenters.image_canvas.background_parts.use_cases import (
        schedule as sched_mod,
    )

    ctx = _ctx_with_widget_ctx()
    presenter = _schedule_presenter(ctx)
    sched_mod.schedule_update(presenter)
    assert presenter._update_scheduler_timer.isActive()
    assert _invalidate_records(ctx) == []

    ctx2 = _ctx_with_widget_ctx()
    fake = _healthy_keepwarm_fake(ctx2)
    fake.runtime_state._tile_more_pending = True
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _keepwarm_timers(fake)
    assert len(timers) == 1
    timers[0].timeout.emit()
    assert fake.updates == 1  # priming preserved
    assert _invalidate_records(ctx2) == []


def test_bus_shape_additive_only():
    """New record kind is additive: generic record()/dump() unchanged."""
    from engine.frame.context import (
        INVALIDATE_PREFIX,
        FrameContext,
    )

    ctx = FrameContext()
    d = ctx.record_invalidation("schedule.fps_timer", "armed interval_ms=16")
    assert d.pass_name == "invalidate.schedule.fps_timer"
    assert d.verdict == "ran"
    assert INVALIDATE_PREFIX == "invalidate."
    assert ctx.invalidations() == [d]
    # plain render decisions and the bus coexist in one dump
    ctx.record("mag_gate", "skipped", "mag_gate dirty=False visible_overlays=0")
    assert len(ctx.invalidations()) == 1
    assert len(ctx) == 2
    assert "invalidate.schedule.fps_timer" in ctx.dump()
    assert "mag_gate" in ctx.dump()
