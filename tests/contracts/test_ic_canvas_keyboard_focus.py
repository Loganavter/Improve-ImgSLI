"""Image Compare canvas-keyboard reachability (real widgets, real events).

Measured live on a private display: in Image Compare the documented canvas
chords — ``←↑↓→`` (pan), ``+``/``-``/``=`` (zoom) and ``D`` (Divider
Visibility) — did nothing, while ``Ctrl+wheel`` zoomed, the ``D`` toolbar
button worked, and Multi Compare's canvas chords all worked in the same
session.

Three seams are pinned here; each one alone leaves a documented chord dead or
kills a loupe key:

A. Router: a chord the ACTIVE TAB's shortcut binder installed is never
   consumed by the global keyboard route (``D`` is both the divider shortcut
   and an overlay-movement key, so routing it globally ate it before the
   shortcut map).
B. Shell: ``ImageCompareWidget`` is the keyboard focus owner and forwards
   ``keyPressEvent`` to its canvas — the ``MultiCompareWidget`` contract —
   because the canvas is a ``QRhiWidget`` and must stay ``NoFocus`` (see
   ``ui/canvas_infra/rhi/rhi_focus.py``: a focused RHI host restacks the
   Vulkan subsurface on Wayland).
C. Re-dispatch: a key the canvas does not accept goes back to the global
   keyboard handler, so loupe movement (``W A S D Q E``) and ``Space`` preview
   keep their routing now that the shell owns focus.

Why the runtime suite is green while the chord is dead:
``src/tabs/image_compare/tests/runtime/test_keyboard_pan_zoom.py`` calls
``handle_key_press_event`` on a fake widget and never exercises reachability
(no focus owner, no router, no shortcut map). These tests go through a real
``QApplication``, real widgets and ``sendEvent`` / ``QTest.keyClick``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

KEYS = {
    "W": Qt.Key.Key_W,
    "A": Qt.Key.Key_A,
    "S": Qt.Key.Key_S,
    "D": Qt.Key.Key_D,
    "Q": Qt.Key.Key_Q,
    "E": Qt.Key.Key_E,
    "Space": Qt.Key.Key_Space,
}


def _key_event(key, event_type=QEvent.Type.KeyPress):
    return QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier)


class _SignalSpy:
    def __init__(self):
        self.events: list = []

    def emit(self, event):
        self.events.append(event)


class _RouterEventHandler(QObject):
    """Minimal ``EventHandler`` stand-in wired to the real router.

    ``eventFilter`` is the same entry point the app installs on
    ``QApplication`` (``ui/main_window/startup.py``), so these tests exercise
    the production decision path, not a restatement of it.
    """

    def __init__(self, keyboard_handler):
        super().__init__()
        self.keyboard_handler = keyboard_handler
        from events.router import route_global_keyboard_event

        self._route = route_global_keyboard_event
        self.global_presses = _SignalSpy()
        self.global_releases = _SignalSpy()
        self.canvas_presses = _SignalSpy()
        self.canvas_releases = _SignalSpy()
        # Same attribute names the real EventHandler exposes to the router.
        self.global_keyboard_press_event_signal = self.global_presses
        self.global_keyboard_release_event_signal = self.global_releases
        self.canvas_keyboard_press_event_signal = self.canvas_presses
        self.canvas_keyboard_release_event_signal = self.canvas_releases

    def eventFilter(self, watched, event):  # noqa: N802
        return self._route(self, watched, event)


class _EmptyTabRegistry:
    """No active tab: the null/foreign-focus case the defect was measured in."""

    def get_active_tab(self):
        return None


def _route_store():
    from types import SimpleNamespace

    return SimpleNamespace(
        viewport=SimpleNamespace(
            interaction_state=SimpleNamespace(
                pressed_keys=set(),
                space_bar_pressed=False,
                last_horizontal_movement_key=None,
                last_vertical_movement_key=None,
                last_spacing_movement_key=None,
            ),
            view_state=SimpleNamespace(showing_single_image_mode=0),
        ),
        emit_viewport_change=lambda *_args, **_kwargs: None,
    )


def _global_keyboard_handler(store=None):
    from types import SimpleNamespace

    from events.app_event.keyboard import GlobalKeyboardHandler
    from events.keyboard_state_service import KeyboardStateService

    store = store or _route_store()
    return GlobalKeyboardHandler(
        store,
        presenter_provider=lambda: None,
        movement_controller=SimpleNamespace(start=lambda: None, stop=lambda: None),
        keyboard_state=KeyboardStateService(store),
    )


@pytest.fixture(autouse=True)
def _deterministic_focus(qapp):
    """No foreign focus owner leaks in from a previous test (offscreen QPA)."""
    focused = QApplication.focusWidget()
    if focused is not None:
        focused.clearFocus()
    QApplication.processEvents()
    yield


@pytest.fixture
def no_active_tab(monkeypatch):
    from events import router as router_mod
    from events.app_event import keyboard as keyboard_mod

    registry = _EmptyTabRegistry()
    monkeypatch.setattr(router_mod, "get_shared_tab_registry", lambda: registry)
    monkeypatch.setattr(keyboard_mod, "get_shared_tab_registry", lambda: registry)
    return registry


@pytest.fixture
def binder_claim(monkeypatch):
    """Install a real ``D`` claim for ``image_compare`` via the live binder."""
    from core.actions.types import ActionDescriptor
    from ui.actions import binder as binder_module
    from ui.actions.binder import ActionShortcutBinder
    from ui.actions.registry import ActionRegistry

    fired: list[str] = []
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="image_compare.divider.visible",
            label_key="image_compare.action.divider_visible",
            owner_tab="image_compare",
            shortcut="D",
            run=lambda: fired.append("image_compare.divider.visible"),
        )
    )
    window = QWidget()
    binder = ActionShortcutBinder()
    binder.resync(window, registry=registry, overrides={}, active_tab="image_compare")
    monkeypatch.setattr(binder_module, "_binder", binder)
    yield fired, window
    window.close()
    window.deleteLater()


def _make_shell(canvas=None):
    from tabs.image_compare.widget import ImageCompareWidget

    shell = ImageCompareWidget()
    if canvas is not None:
        shell.image_label = canvas
    return shell


def _real_canvas():
    from tabs.image_compare.canvas.widget import CanvasWidget

    return CanvasWidget()


class _RecordingCanvas:
    """Canvas stand-in that records keys and never accepts them."""

    def __init__(self):
        self.pressed: list[int] = []
        self.released: list[int] = []

    def keyPressEvent(self, event):  # noqa: N802
        self.pressed.append(event.key())

    def keyReleaseEvent(self, event):  # noqa: N802
        self.released.append(event.key())


# --------------------------------------------------------------------------
# B — the shell forwards keys to its canvas
# --------------------------------------------------------------------------


def test_shell_forwards_key_press_to_canvas(qapp):
    """(a) A key on the IC shell reaches the canvas (MC contract)."""
    canvas = _RecordingCanvas()
    shell = _make_shell(canvas)
    try:
        event = _key_event(Qt.Key.Key_Right)
        QApplication.sendEvent(shell, event)
        assert canvas.pressed == [Qt.Key.Key_Right], (
            "ImageCompareWidget did not forward keyPressEvent to its canvas — "
            "the shell is the only focus owner a NoFocus QRhiWidget can rely on"
        )
    finally:
        shell.deleteLater()


def test_arrow_on_shell_pans_the_real_canvas(qapp):
    """(d) Arrow with the IC shell focused actually pans (canvas state moves)."""
    from ui.canvas_infra.viewport.state import get_pan_offset_x

    canvas = _real_canvas()
    shell = _make_shell(canvas)
    shell.show()
    QApplication.processEvents()
    try:
        before = get_pan_offset_x(canvas)
        event = _key_event(Qt.Key.Key_Right)
        QApplication.sendEvent(shell, event)
        after = get_pan_offset_x(canvas)
        assert event.isAccepted()
        assert after > before, (
            f"arrow Right on the focused shell did not pan the canvas "
            f"(pan_x {before} -> {after})"
        )
    finally:
        shell.close()
        shell.deleteLater()


def test_canvas_focus_policy_stays_no_focus(qapp):
    """D — the fix must not move focus onto the QRhiWidget host."""
    canvas = _real_canvas()
    try:
        assert canvas.focusPolicy() == Qt.FocusPolicy.NoFocus, (
            "the IC canvas is a QRhiWidget: rhi_focus.py parks focus off it on "
            "Wayland/Vulkan, so its focus policy must stay NoFocus"
        )
    finally:
        canvas.deleteLater()


# --------------------------------------------------------------------------
# A — the router never consumes a chord the active tab's binder installed
# --------------------------------------------------------------------------


def test_router_does_not_consume_tab_owned_chord(
    qapp, no_active_tab, binder_claim, monkeypatch
):
    """(b) ``D`` at the router, null focus: not consumed by the global route."""
    fired, window = binder_claim
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    try:
        handler = _RouterEventHandler(_global_keyboard_handler())
        event = _key_event(Qt.Key.Key_D)
        consumed = handler._route(handler, None, event)
        assert consumed is False, (
            "the router consumed 'D' before the shortcut map — a chord the "
            "active tab's binder installed must survive global routing"
        )
        assert handler.global_presses.events == [], (
            "the divider chord was routed to the loupe global handler"
        )
    finally:
        window.close()


def test_router_let_through_chord_fires_the_shortcut_end_to_end(
    qapp, no_active_tab, binder_claim, monkeypatch
):
    """(b, end-to-end) Router leaves ``D`` alone, the shortcut map then fires.

    Composed explicitly on purpose: a simulated ``QTest`` key press is matched
    by ``QShortcutMap`` *before* widget-level application filters run (probed
    on this Qt build), so a single key click cannot show what the router ate.
    The router decision is therefore the first half; the shortcut activation
    over the real window is the second. The runtime suite this replaces only
    ever did the second half — which is why it stayed green with the chord
    dead.
    """
    fired, window = binder_claim
    handler = _RouterEventHandler(_global_keyboard_handler())
    try:
        consumed = handler._route(handler, None, _key_event(Qt.Key.Key_D))
        assert consumed is False, (
            "pressing 'D' is consumed by the global router before the tab's "
            "shortcut gets the chance to fire"
        )
        window.show()
        window.activateWindow()
        QApplication.processEvents()
        QTest.keyClick(window, Qt.Key.Key_D)
        QApplication.processEvents()
        assert fired == ["image_compare.divider.visible"], (
            "the installed divider shortcut does not fire for a real 'D' key "
            "press on a focused window"
        )
    finally:
        window.close()


def test_global_routing_table_unchanged_for_loupe_keys(
    qapp, no_active_tab, binder_claim, monkeypatch
):
    """#4 — ``should_route_globally`` keeps its table; the guard is in the router."""
    from events.app_event.keyboard import active_tab_shortcut_owns_event

    handler = _global_keyboard_handler()
    for name, key in KEYS.items():
        assert handler.should_route_globally(_key_event(key), None) is True, (
            f"{name} stopped routing globally: the loupe/preview routing table "
            f"must not change (only the binder-owned chord check may)"
        )
    assert active_tab_shortcut_owns_event(_key_event(Qt.Key.Key_D)) is True
    assert active_tab_shortcut_owns_event(_key_event(Qt.Key.Key_W)) is False


def test_binder_owns_chord_is_scoped_to_its_tab(qapp, binder_claim):
    """The claim lookup is the binder's, and it is tab-scoped (interface D)."""
    from ui.actions.binder import get_action_shortcut_binder

    binder = get_action_shortcut_binder()
    assert binder.owns_chord("D") is True
    assert binder.owns_chord(" d ") is True  # normalized, not string-matched
    assert binder.owns_chord("D", active_tab="image_compare") is True
    assert binder.owns_chord("D", active_tab="multi_compare") is False
    assert binder.owns_chord("") is False
    assert binder.owns_chord("Ctrl+Shift+Q") is False


# --------------------------------------------------------------------------
# C — unaccepted keys are re-dispatched, the divider chord is not
# --------------------------------------------------------------------------


def test_unaccepted_key_is_redispatched_to_global_handler(qapp, no_active_tab):
    """(c) ``W`` the canvas rejects still reaches the global loupe path."""
    canvas = _RecordingCanvas()
    shell = _make_shell(canvas)
    handler = _RouterEventHandler(_global_keyboard_handler())
    shell.event_handler = handler
    try:
        event = _key_event(Qt.Key.Key_W)
        QApplication.sendEvent(shell, event)
        assert canvas.pressed == [Qt.Key.Key_W]
        assert handler.global_presses.events == [event], (
            "an unaccepted 'W' died in the shell instead of being "
            "re-dispatched to the global keyboard handler"
        )
    finally:
        shell.deleteLater()


def test_divider_chord_is_not_redispatched_to_the_loupe(
    qapp, no_active_tab, binder_claim, monkeypatch
):
    """C's counterpart: a binder-owned chord belongs to the shortcut map."""
    canvas = _RecordingCanvas()
    shell = _make_shell(canvas)
    handler = _RouterEventHandler(_global_keyboard_handler())
    shell.event_handler = handler
    try:
        event = _key_event(Qt.Key.Key_D)
        QApplication.sendEvent(shell, event)
        assert canvas.pressed == [Qt.Key.Key_D]
        assert handler.global_presses.events == [], (
            "'D' was re-dispatched to the loupe handler — the divider chord "
            "must only reach the tab's shortcut map"
        )
    finally:
        shell.deleteLater()


def test_key_release_is_symmetric(qapp, no_active_tab):
    """Held loupe movement needs the release too (loupe stops on release)."""
    canvas = _RecordingCanvas()
    shell = _make_shell(canvas)
    handler = _RouterEventHandler(_global_keyboard_handler())
    shell.event_handler = handler
    try:
        event = _key_event(Qt.Key.Key_W, QEvent.Type.KeyRelease)
        QApplication.sendEvent(shell, event)
        assert canvas.released == [Qt.Key.Key_W]
        assert handler.global_releases.events == [event]
    finally:
        shell.deleteLater()


# --------------------------------------------------------------------------
# D — a hidden toolbar slot must not remove the keyboard shortcut
# --------------------------------------------------------------------------
#
# Live cause of the dead `D`: `registry.list_for()` filtered the action out
# because its target button is hidden in the simple UI mode
# (`_action_chrome_is_available`), so `binder.resync` never saw it, `_claimed`
# had no `D`, and the router (correctly) routed the key globally. The two
# questions — "list it in Find Action" and "may it own a shortcut" — are
# separate: a hidden button is still a live target.


def _registry_with_hidden_target():
    from core.actions.types import ActionDescriptor, ActionTarget
    from ui.actions.registry import ActionRegistry

    button = QWidget()
    button.hide()
    registry = ActionRegistry()
    registry.register(
        ActionDescriptor(
            action_id="image_compare.divider.visible",
            label_key="image_compare.action.divider_visible",
            owner_tab="image_compare",
            topic="divider",
            shortcut="D",
            run=lambda: None,
            target=ActionTarget(widget=button),
        )
    )
    return registry, button


def test_chrome_filter_hides_the_action_but_shortcut_scope_keeps_it(qapp):
    """Find Action still hides a hidden-button action; the binder must not."""
    registry, _button = _registry_with_hidden_target()
    assert registry.list_for(active_tab="image_compare") == []
    kept = [
        action.action_id
        for action in registry.list_for(active_tab="image_compare", chrome_only=False)
    ]
    assert kept == ["image_compare.divider.visible"]


def test_binder_installs_a_chord_whose_button_is_hidden(qapp):
    """`D` survives a UI mode that hides the divider button."""
    from ui.actions.binder import ActionShortcutBinder

    registry, _button = _registry_with_hidden_target()
    window = QWidget()
    binder = ActionShortcutBinder()
    binder.resync(window, registry=registry, overrides={}, active_tab="image_compare")
    try:
        assert binder.owns_chord("D", active_tab="image_compare") is True
        assert binder.owns_chord("D", active_tab="multi_compare") is False
    finally:
        window.close()
        window.deleteLater()
