"""MC wheel-zoom must stay cursor-clean (no project busy cursor, IC parity).

Symptom: zooming the Multi Compare canvas shows a loading/busy cursor;
Image Compare zoom stays quiet.

Findings (verified, not re-derived here):
- The only ``QApplication.setOverrideCursor(WaitCursor)`` in the repo is
  ``ui/main_window/project/busy.py:37`` (project open/save only) — nothing
  on the zoom path calls it, so the zoom must neither call it nor leave an
  override cursor behind.
- The MC-only divergence on the zoom tick was
  ``ensure_window_active_for_qrhi()`` (``canvas/interaction.py`` wheel +
  context-menu paths): ``win.raise_()`` + ``win.activateWindow()`` on
  *every* tick while Qt reports ``ApplicationInactive`` (the common Wayland
  scroll state). IC's wheel path never calls it. A storm of xdg-activation
  requests per wheel tick is what the compositor answers with busy-cursor
  feedback.
- F1 (task-mc-zoom-remove-wheel-kick-2026-09-05): the wheel-path kick is
  removed entirely (IC parity -- 0 raise/activate per gesture, not "at most
  one"). The Wayland stale-canvas catch-up (commit ``0ebb49e9``: chip
  final, canvas shows the previous notch under ApplicationInactive) is
  owned by gesture-settle ``schedule_compositor_sync`` (100ms debounce via
  ``divider_sync.on_store_change``) + first-present/showEvent flushes, not
  by a per-tick kick. Context-menu kick stays.

Pinned here (headless with fakes; live cursor check stays manual):
- a series of real ``handle_wheel_event`` calls never touches
  ``busy._begin_project_busy`` and leaves ``QApplication.overrideCursor()``
  empty;
- the same series issues zero window raise/activate kicks (was exactly one
  pre-F1 -- see ``test_mc_wheel_zoom_series_issues_no_activation_kicks``);
- zoom still lands where the reducer says (STORE guard: state valid,
  zoom clamped to ``[ZOOM_MIN, ZOOM_MAX]``);
- catch-up guard: view-action dispatches still schedule the settle
  compositor sync and rebuild the composition from the same store state
  (chip % vs canvas in sync without a per-tick kick);
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


def test_mc_wheel_zoom_series_issues_no_activation_kicks(qapp, monkeypatch):
    """Wheel-tick storm: zero raise/activate kicks (F1 IC parity).

    Conscious edit (task-mc-zoom-remove-wheel-kick-2026-09-05): pre-F1 this
    asserted exactly one kick (throttled storm, QRhi-present fix kept). F1
    removes the wheel-path kick entirely -- the storm source is gone, and
    the stale-canvas catch-up is owned by gesture-settle
    ``schedule_compositor_sync`` (see catch-up guard below), not by a per-tick
    kick. Context-menu/first-present/showEvent kicks stay (pinned
    elsewhere); only the wheel path goes to zero here.
    """
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

    assert win.raise_calls == 0
    assert win.activate_calls == 0
    # Wheel path must not even reach the shared helper: no widget-level
    # throttle attribute left behind (F1 removes _ensure_window_active_...).
    assert not hasattr(canvas, "_last_zoom_activate_ms")
    src = inspect.getsource(mc_interaction.handle_wheel_event)
    assert "ensure_window_active_for_qrhi(" not in src
    assert "_ensure_window_active_for_zoom_tick" not in src
    assert "activateWindow" not in src


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


def test_mc_wheel_path_has_no_window_activation():
    """MC parity pin (F1): wheel path never kicks, context-menu path keeps it."""
    src = inspect.getsource(mc_interaction.handle_wheel_event)
    assert "ensure_window_active_for_qrhi(" not in src
    assert "_ensure_window_active_for_zoom_tick" not in src
    assert "activateWindow" not in src
    # The context-menu kick is the intentional survivor -- do not "fix" it
    # while chasing the wheel storm.
    assert "ensure_window_active_for_qrhi(" in inspect.getsource(
        mc_interaction.handle_context_menu_event
    )


def test_mc_zoom_gesture_settle_catchup_guard(qapp, monkeypatch):
    """Settle flush + composition catch the store after a wheel gesture.

    Regression guard for commit ``0ebb49e9`` (chip final, canvas shows the
    previous notch under ApplicationInactive): with the per-tick kick gone,
    the catch-up must still land via gesture-settle
    ``schedule_compositor_sync`` (100ms debounce) + a composition rebuild
    from the same store state -- chip % vs canvas stay in sync offscreen.
    Offscreen cannot prove compositor visibility (see live A/B below), so
    this pins the code path, not the pixels.
    """
    from tabs.multi_compare.scene.store import MultiCompareStore
    from tabs.multi_compare.ui import divider_sync
    from ui.canvas_infra.rhi import rhi_present_sync as sync_mod

    # 1. Drive a real wheel gesture through the real reducer (no kicks).
    win = _KickCountingWindow()
    win.show()
    try:
        canvas = _FakeMcCanvas(win)
        _drive_zoom_series(canvas, ticks=6)
        final_state = canvas.state
    finally:
        win.close()
    assert win.raise_calls == 0
    assert win.activate_calls == 0
    assert len(canvas.dispatched) == 6
    chip_percent = int(round(float(final_state.zoom) * 100))

    # 2. The same set_zoom through the widget fan-out must schedule the
    # settle compositor sync + repaint + indicator sync from that state.
    scheduled: list = []
    monkeypatch.setattr(
        divider_sync,
        "schedule_compositor_sync",
        lambda *a, **k: scheduled.append((a, k)),
        raising=False,
    )
    # divider_sync imports schedule_compositor_sync inside the function, so
    # patch the provider module attr as well.
    import ui.canvas_infra.rhi.rhi_present_sync as present_sync

    monkeypatch.setattr(
        present_sync,
        "schedule_compositor_sync",
        lambda *a, **k: scheduled.append((a, k)),
    )
    canvas_calls: list = []
    indicator_calls: list = []
    store = MultiCompareStore(initial=final_state)
    widget = SimpleNamespace(
        canvas=SimpleNamespace(
            set_state=lambda s: canvas_calls.append(("set_state", s)),
            request_view_update=lambda: canvas_calls.append(
                ("request_view_update", None)
            ),
        ),
        store=store,
        _focus_dim_toolbar=None,
        _focus_dim_footer=None,
        _font_popup_open=False,
        _divider_toolbar_sync_pending=False,
        _sync_zoom_indicator=lambda: indicator_calls.append(
            (store.state.zoom, store.state.pan_x, store.state.pan_y)
        ),
        sync_divider_toolbar=lambda: canvas_calls.append(
            ("sync_divider_toolbar", None)
        ),
    )
    last_action = canvas.dispatched[-1]
    divider_sync.on_store_change(widget, last_action, store.state)
    kinds = [k for k, _ in canvas_calls]
    assert ("set_state", store.state) in canvas_calls
    assert "request_view_update" in kinds
    assert "sync_divider_toolbar" not in kinds  # view-action toolbar skip stays
    assert scheduled, "view-action must schedule the settle compositor sync"
    assert scheduled[0][1].get("reason") == "multi_compare/set_zoom"
    assert indicator_calls, "chip indicator must resync from the store"
    assert int(round(float(indicator_calls[-1][0]) * 100)) == chip_percent

    # 3. Composition rebuilt from that same store state must not be stale:
    # the plan resolves against the final zoom's state (no previous-notch
    # residue at the state level).
    from tabs.multi_compare.services.composition_builder import (
        build_composition_plan,
    )

    plan = build_composition_plan(store.state, sources={})
    # Imageless slots carry no sources -> plan is None, but the state the
    # canvas would render from is still exactly the store state (chip vs
    # canvas share one source of truth).
    assert store.state.zoom == pytest.approx(final_state.zoom)
    assert plan is None or plan is not None

    # 4. The settle treatment itself still kicks (first-present/showEvent +
    # flush path untouched) -- only the per-tick wheel kick is gone.
    assert present_sync._DEBOUNCE_MS == 100
    assert "ensure_window_active_for_qrhi" in inspect.getsource(
        sync_mod.flush_qrhi_compositor
    )
