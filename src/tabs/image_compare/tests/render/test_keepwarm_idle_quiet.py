"""Keep-warm idle quiet: healthy idle must not tick endlessly.

Regression for queue task-ic-keepwarm-idle-2026-09-13: eight identical
``gap draw_plan entries=8 side1=4 side2=4 grid 2x2`` lines ~250ms apart
while img_sig was unchanged and coverage healthy 1.0. Source is
``canvas/widget.py`` ``_ensure_dnd_keepwarm`` (periodic QTimer calling
``update()`` with stand-down only for hidden/minimized/drag overlay) plus
the unconditional gap ``draw_plan`` log in
``canvas/rhi_renderer/draw_plan.py`` (no sig dedup, unlike
``renderer.py:361`` / ``coverage.py:257`` / ``fallback.py:183``).

Healthy idle with an unchanged sig across many keep-warm ticks must build
the draw plan at most twice and emit the gap draw_plan log at most once;
a busy renderer (more-pending) must still tick so the pipeline stays
primed.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _base_image():
    return SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )


def _make_2x2_service():
    from engine.cache.tile_texture_service import TileTextureService

    service = TileTextureService(max_tile_extent=1024)
    service.register_source("img1", (2048, 2048))  # 2x2 grid
    service.register_source("img2", (2048, 2048))  # 2x2 grid
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("img1", index, byte_size=100, content_size=(1024, 1024))
        service.mark_resident("img2", index, byte_size=100, content_size=(1024, 1024))
    return service


def _timers_of(fake):
    from PySide6.QtCore import QTimer

    return [t for t in fake.findChildren(QTimer) if t.interval() > 0]


def _healthy_fake():
    from PySide6.QtCore import QObject

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


def test_healthy_idle_keepwarm_ticks_stay_quiet(qapp, monkeypatch):
    """8 keep-warm ticks on healthy idle: <=2 plan builds, <=1 gap log."""
    import tabs.image_compare.canvas.rhi_renderer.draw_plan as dp_mod
    from tabs.image_compare.canvas import widget as wmod

    monkeypatch.delenv("IMGSLI_DND_KEEPWARM_MS", raising=False)
    dp_mod._last_gap_draw_plan_sig = None
    monkeypatch.setattr(dp_mod, "_gap_enabled", lambda: True)
    gap_draw_plan_logs: list = []
    _orig_gap_log = dp_mod._gap_log

    def _counting_gap_log(msg, *a, **kw):
        if isinstance(msg, str) and msg.startswith("gap draw_plan"):
            gap_draw_plan_logs.append((msg, a))
        return _orig_gap_log(msg, *a, **kw)

    monkeypatch.setattr(dp_mod, "_gap_log", _counting_gap_log)

    service = _make_2x2_service()
    base = _base_image()
    keys = ("img1", "img2")

    _orig_build = dp_mod.build_array_draw_plan
    builds: list = []

    def _counting_build(*a, **kw):
        items = _orig_build(*a, **kw)
        builds.append(len(items))
        return items

    monkeypatch.setattr(dp_mod, "build_array_draw_plan", _counting_build)

    fake = _healthy_fake()
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _timers_of(fake)
    assert len(timers) == 1
    timer = timers[0]
    first_len: int | None = None
    for _ in range(8):
        timer.timeout.emit()
        if fake.updates:
            # Simulate the render this update would have produced.
            items = _orig_build(
                service, keys, base, diff_key=None, sampler_name="linear"
            )
            if first_len is None:
                first_len = len(items)
            assert len(items) == first_len  # unchanged sig -> identical plan
    # The keep-warm tick itself must stand down on healthy idle...
    assert fake.updates <= 2
    # ...so the draw plan is (re)built at most twice...
    assert len(builds) <= 2
    # ...and the gap draw_plan log fires at most once for identical frames.
    assert len(gap_draw_plan_logs) <= 1


def test_gap_draw_plan_log_dedups_identical_frames(qapp, monkeypatch):
    """Direct draw_plan check: 8 identical builds emit the log at most once."""
    import tabs.image_compare.canvas.rhi_renderer.draw_plan as dp_mod

    dp_mod._last_gap_draw_plan_sig = None
    monkeypatch.setattr(dp_mod, "_gap_enabled", lambda: True)
    gap_draw_plan_logs: list = []
    _orig_gap_log = dp_mod._gap_log

    def _counting_gap_log(msg, *a, **kw):
        if isinstance(msg, str) and msg.startswith("gap draw_plan"):
            gap_draw_plan_logs.append((msg, a))
        return _orig_gap_log(msg, *a, **kw)

    monkeypatch.setattr(dp_mod, "_gap_log", _counting_gap_log)

    service = _make_2x2_service()
    base = _base_image()
    keys = ("img1", "img2")
    first_len: int | None = None
    for _ in range(8):
        items = dp_mod.build_array_draw_plan(
            service, keys, base, diff_key=None, sampler_name="linear"
        )
        assert items
        if first_len is None:
            first_len = len(items)
        assert len(items) == first_len
    assert len(gap_draw_plan_logs) <= 1


def test_busy_renderer_keepwarm_still_primes(qapp, monkeypatch):
    """Guard against over-suppression: more-pending must still tick."""
    from tabs.image_compare.canvas import widget as wmod

    monkeypatch.delenv("IMGSLI_DND_KEEPWARM_MS", raising=False)
    fake = _healthy_fake()
    fake.runtime_state._tile_more_pending = True
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _timers_of(fake)
    assert len(timers) == 1
    for _ in range(8):
        timers[0].timeout.emit()
    assert fake.updates == 8
