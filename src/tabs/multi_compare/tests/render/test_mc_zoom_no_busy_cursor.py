"""MC wheel-zoom must stay cursor-clean (no project busy cursor, IC parity).

Symptom: zooming the Multi Compare canvas shows a loading/busy cursor;
Image Compare zoom stays quiet.

Findings (verified, not re-derived here):
- The only ``QApplication.setOverrideCursor(WaitCursor)`` in the repo is
  ``ui/main_window/project/busy.py:37`` (project open/save only) — nothing
  on the zoom path calls it, so the zoom must neither call it nor leave an
  override cursor behind.
- The MC-only divergence on the zoom tick is
  ``ensure_window_active_for_qrhi()`` (``canvas/interaction.py`` wheel +
  context-menu paths): ``win.raise_()`` + ``win.activateWindow()`` on
  *every* tick while Qt reports ``ApplicationInactive`` (the common Wayland
  scroll state). IC's wheel path never calls it. A storm of xdg-activation
  requests per wheel tick is what the compositor answers with busy-cursor
  feedback, so the shared helper throttles repeat kicks (cooldown) instead
  of firing per tick.

Pinned here (headless with fakes; live cursor check stays manual):
- a series of real ``handle_wheel_event`` calls never touches
  ``busy._begin_project_busy`` and leaves ``QApplication.overrideCursor()``
  empty;
- the same series issues at most one window raise/activate kick (storm
  throttled) while still issuing one (QRhi-present fix not ripped out);
- zoom still lands where the reducer says (STORE guard: state valid,
  zoom clamped to ``[ZOOM_MIN, ZOOM_MAX]``);
- IC parity: IC's canvas interaction source never references the
  window-activation helper.

Live verification (for a human, Wayland+Mutter): open MC with 2+ images,
scroll-zoom in/out several notches — no loading cursor at any point;
zoom % chip and canvas stay in sync.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QWidget

from tabs.multi_compare.canvas import interaction as mc_interaction
from tabs.multi_compare.models import CompareSlot, LeafNode, MultiCompareState
from tabs.multi_compare.scene import actions
from tabs.multi_compare.scene.store import reduce as mc_reduce
from ui.canvas_infra.rhi import rhi_present_sync as sync
from ui.main_window.project import busy

import pytest


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    assert QApplication.overrideCursor() is None


class _KickCountingWindow(QWidget):
    """Visible stand-in for the main window; counts activation kicks."""

    def __init__(self):
        super().__init__()
        self.raise_calls = 0
        self.activate_calls = 0

    def raise_(self):  # noqa: N802 — Qt API
        self.raise_calls += 1

    def activateWindow(self):  # noqa: N802 — Qt API
        self.activate_calls += 1


class _WheelEvent:
    def __init__(self, delta_y=120, pos=None):
        self._delta_y = delta_y
        self._pos = pos if pos is not None else QPoint(50, 40)
        self.accepted = False
        self.ignored = False

    def angleDelta(self):
        return SimpleNamespace(y=lambda: self._delta_y)

    def position(self):
        return SimpleNamespace(toPoint=lambda: self._pos)

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


class _FakeMcCanvas:
    """Minimal canvas for ``handle_wheel_event``: real state + real reducer."""

    ZOOM_MIN = 1.0
    ZOOM_MAX = 50.0
    ZOOM_STEP = 1.1

    def __init__(self, window):
        self._window = window
        self.pixel_cache = None
        self.state = MultiCompareState(
            slots=[CompareSlot(id=7, path=None, label="")],
            zoom=2.0,
            pan_x=0.0,
            pan_y=0.0,
        )
        self.dispatched: list = []

    def window(self):
        return self._window

    def _leaf_rects(self):
        return [(LeafNode(slot_id=7), QRect(0, 0, 400, 300))]

    def _do_dispatch(self, action):
        self.dispatched.append(action)
        self.state = mc_reduce(self.state, action)


def _drive_zoom_series(canvas, *, ticks=12, delta_y=120):
    for _ in range(ticks):
        mc_interaction.handle_wheel_event(canvas, _WheelEvent(delta_y=delta_y))


def test_mc_wheel_zoom_series_leaves_no_override_cursor(qapp, monkeypatch):
    """Series of wheel-zoom ticks: busy.py untouched, override cursor empty."""
    begin_calls: list = []
    monkeypatch.setattr(
        busy, "_begin_project_busy", lambda *a, **k: begin_calls.append((a, k))
    )
    # Wayland scroll state: window visible but Qt reports Inactive, which is
    # exactly when the per-tick activation kick used to fire every tick.
    monkeypatch.setattr(
        qapp,
        "applicationState",
        lambda: Qt.ApplicationState.ApplicationInactive,
    )
    monkeypatch.setattr(sync, "_LAST_ACTIVE_KICK_MS", None)
    win = _KickCountingWindow()
    win.show()
    try:
        canvas = _FakeMcCanvas(win)
        _drive_zoom_series(canvas, ticks=12)
    finally:
        win.close()

    assert begin_calls == []
    assert QApplication.overrideCursor() is None
    # Zoom itself still works through the real reducer (STORE guard).
    assert len(canvas.dispatched) == 12
    assert all(a.type == "multi_compare/set_zoom" for a in canvas.dispatched)
    expected = 2.0 * (canvas.ZOOM_STEP**12)
    assert canvas.state.zoom == pytest.approx(expected)
    assert canvas.ZOOM_MIN <= canvas.state.zoom <= canvas.ZOOM_MAX


def test_mc_wheel_zoom_series_throttles_activation_kicks(qapp, monkeypatch):
    """Wheel-tick storm: at most one raise/activate kick, but still one."""
    monkeypatch.setattr(
        qapp,
        "applicationState",
        lambda: Qt.ApplicationState.ApplicationInactive,
    )
    monkeypatch.setattr(sync, "_LAST_ACTIVE_KICK_MS", None)
    win = _KickCountingWindow()
    win.show()
    try:
        canvas = _FakeMcCanvas(win)
        _drive_zoom_series(canvas, ticks=12)
    finally:
        win.close()

    assert win.raise_calls <= 1
    assert win.activate_calls <= 1
    # The QRhi-present fix must survive throttling: the first tick in an
    # inactive window still kicks once.
    assert win.raise_calls == 1
    assert win.activate_calls == 1


def test_ic_wheel_path_has_no_window_activation():
    """IC parity pin: IC canvas interaction never kicks window activation."""
    from tabs.image_compare.canvas import interaction as ic_interaction

    assert "ensure_window_active_for_qrhi" not in inspect.getsource(ic_interaction)
    assert "activateWindow" not in inspect.getsource(ic_interaction)


def test_keyboard_zoom_path_leaves_no_override_cursor(qapp, monkeypatch):
    """Keyboard zoom dispatches set_zoom without touching the busy cursor."""
    begin_calls: list = []
    monkeypatch.setattr(
        busy, "_begin_project_busy", lambda *a, **k: begin_calls.append((a, k))
    )
    state = MultiCompareState(
        slots=[CompareSlot(id=7, path=None, label="")],
        zoom=2.0,
        pan_x=0.1,
        pan_y=0.2,
    )
    dispatched: list = []

    class _KeyCanvas(_FakeMcCanvas):
        def __init__(self):
            self.state = state
            self.dispatched = dispatched

        def _leaf_rects(self):
            return []

        def rect(self):
            return QRect(0, 0, 1000, 800)

    from tabs.multi_compare.canvas import interaction as mc_keys

    class _KeyEvent:
        def key(self):
            return Qt.Key.Key_Plus

        def accept(self):
            pass

    widget = _KeyCanvas()
    mc_keys.handle_key_press_event(widget, _KeyEvent())
    assert dispatched and dispatched[-1].type == "multi_compare/set_zoom"
    assert begin_calls == []
    assert QApplication.overrideCursor() is None
    _ = actions  # reducer-shape import guard (actions stay the dispatch_format)
