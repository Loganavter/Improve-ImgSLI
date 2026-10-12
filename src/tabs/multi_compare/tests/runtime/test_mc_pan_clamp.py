"""Cover-range pan clamp for the Multi Compare canvas (QuickLook parity).

Regression tests for the free-pan bug: ``clamp_pan_values`` used to be a
no-op, so middle-drag could push the image fully out of its cell, and the
wheel path anchored to unclamped cursor UV, so zooming in a (letterboxed)
corner pushed the image away and showed void. Mirrors QuickLook's
``preview_zoom.clamp_pan``/``wheel_zoom_pan`` cover rule
(``|pan| <= (cover-1)/(2*cover)``, ``cover = fit*zoom``; floor forces
origin).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QImage

from tabs.multi_compare.canvas import interaction as mc_interaction
from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
)
from tabs.multi_compare.pipeline.cache import MultiComparePixelCache
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.scene.store import MultiCompareStore


def test_clamp_pan_floor_forces_origin():
    assert mc_interaction.clamp_pan_values(0.4, -0.3, 1.0, 1.0, 0.75) == (0.0, 0.0)
    assert mc_interaction.clamp_pan_values(10.0, 10.0, 1.0, 1.0, 1.0) == (0.0, 0.0)


def test_clamp_pan_cover_range_when_zoomed():
    assert mc_interaction.clamp_pan_values(0.0, 0.0, 2.0, 1.0, 0.75) == (0.0, 0.0)
    got = mc_interaction.clamp_pan_values(10.0, -10.0, 2.0, 1.0, 0.75)
    assert got == pytest.approx((0.25, -1.0 / 6.0))
    # inside the range stays untouched
    assert mc_interaction.clamp_pan_values(0.1, 0.05, 2.0, 1.0, 0.75) == (0.1, 0.05)


def test_clamp_pan_fail_open():
    assert mc_interaction.clamp_pan_values(0.1, 0.2, 2.0, 0.0, -1.0) == (0.1, 0.2)
    assert mc_interaction.clamp_pan_values(0.1, 0.2, float("nan")) == (0.1, 0.2)


class _WheelEvent:
    def __init__(self, delta, x=100, y=100):
        self._delta = delta
        self._pos = QPoint(x, y)
        self.accepted = False
        self.ignored = False

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._delta)

    def position(self):
        pos = self._pos
        return SimpleNamespace(
            toPoint=lambda: pos,
            x=lambda: float(pos.x()),
            y=lambda: float(pos.y()),
        )

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _slot_image(tmp_path, name="img0.png", w=64, h=48):
    p = tmp_path / name
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(0x808080)
    assert img.save(str(p))
    return p


@pytest.fixture()
def wheel_env(tmp_path):
    cache = MultiComparePixelCache()
    path = _slot_image(tmp_path)
    cache.put_preview(path, QImage(str(path)))
    slot = CompareSlot(id=1, path=path, label="t", revision=0)
    store = MultiCompareStore(initial=MultiCompareState(slots=[slot]))
    rects = [(LeafNode(1), QRect(0, 0, 200, 200))]

    class _FakeCanvas:
        ZOOM_MIN = 1.0
        ZOOM_MAX = 50.0
        ZOOM_STEP = 1.1

    w = _FakeCanvas()
    w.state = store.state
    w.pixel_cache = cache
    dispatched = []

    def _do_dispatch(action):
        dispatched.append(action)
        store.dispatch(action)
        w.state = store.state

    w._do_dispatch = _do_dispatch
    w._leaf_rects = lambda: rects
    w.dispatched = dispatched
    return SimpleNamespace(widget=w, store=store, slot=slot)


def test_wheel_corner_zoom_stays_covered(wheel_env):
    """Zooming over a letterboxed corner anchors to the image edge (IC
    uv-clamp parity) and the result stays in the cover range.

    64x48 in a 200x200 cell -> fit (1.0, 0.75). At zoom 1 the Y axis is
    letterboxed, so a corner tick must leave pan_y at 0 instead of
    dragging the image off (old math gave -0.0594).
    """
    w = wheel_env.widget
    mc_interaction.handle_wheel_event(w, _WheelEvent(120, x=198, y=198))
    assert len(w.dispatched) == 1
    action = w.dispatched[0]
    assert action.zoom == pytest.approx(1.1)
    assert action.pan_x == pytest.approx(-0.0445, abs=1e-4)
    assert action.pan_y == 0.0


def test_drag_beyond_edge_clamps_to_cover(monkeypatch):
    """A huge middle-drag parks at the cover edge, never in the void."""
    monkeypatch.setattr(mc_interaction, "iter_active", lambda _w: ())
    dispatched = []

    widget = SimpleNamespace(
        state=SimpleNamespace(zoom=2.0, pan_x=0.0, pan_y=0.0),
        _panning=True,
        _pan_start_pos=QPointF(100.0, 100.0),
        _pan_start_state=(0.0, 0.0),
        _pan_ref_rect=QRect(0, 0, 200, 200),
        _pan_ref_fit=(1.0, 0.75),
        _do_dispatch=dispatched.append,
        setCursor=lambda _c: None,
    )

    class _MoveEvent:
        def position(self):
            return QPointF(2100.0, 100.0)

        def buttons(self):
            from PySide6.QtCore import Qt

            return Qt.MouseButton.NoButton

        def accept(self):
            pass

    mc_interaction.handle_mouse_move_event(widget, _MoveEvent())
    assert len(dispatched) == 1
    action = dispatched[0]
    assert action.type == "multi_compare/set_pan"
    # x parks at the cover edge (0.25), y stays centered
    assert action.pan_x == pytest.approx(0.25)
    assert action.pan_y == 0.0


def test_keyboard_zoom_out_clamps_carried_pan():
    """Zooming out narrows the cover range, so carried pan is clamped."""
    from PySide6.QtCore import Qt

    from tabs.multi_compare.tests.runtime.test_keyboard_pan_zoom import (
        _KeyEvent,
        _mc_fake_widget,
    )

    widget = _mc_fake_widget(zoom=2.0, pan_x=0.25, pan_y=0.25)
    mc_interaction.handle_key_press_event(widget, _KeyEvent(Qt.Key.Key_Minus))
    action = widget.dispatched[-1]
    assert action.type == "multi_compare/set_zoom"
    assert action.zoom == pytest.approx(2.0 / 1.1)
    cover = 2.0 / 1.1
    edge = (cover - 1.0) / (2.0 * cover)
    assert action.pan_x == pytest.approx(edge)
    assert action.pan_y == pytest.approx(edge)
