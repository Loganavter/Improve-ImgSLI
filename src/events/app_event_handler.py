from PySide6.QtCore import QEvent, QObject, Qt, Signal, QTimer
from PySide6.QtGui import (
    QMouseEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget
from events.app_event import (
    route_main_window_event,
)
from events.drag_drop_handler import DragAndDropService
from events.router import route_drag_and_drop_override, route_global_keyboard_event
from events.runtime import build_event_handler_runtime
from core.log_names import APP_LOGGER_NAME

import logging
import os

# FOCUS/KEY-routing trace lines are extremely high-volume once --debug is on
# (every focus change, every key press) and drown out other subsystems'
# debug output (e.g. IMGSLI_RESIZE_DEBUG render tracing). Gated on its own
# opt-in flag, off by default even under --debug -- same convention as
# shared/rendering/render_debug.py's IMGSLI_RESIZE_DEBUG.
logger = logging.getLogger(f"{APP_LOGGER_NAME}.nav")
if os.environ.get("UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)



def focus_move_stays_inside(old_focus, new_focus) -> bool:
    """True when a settled focus move stays in the same focus context.

    A click on the Image Compare canvas moves focus shell -> canvas -> shell:
    the two widgets are ancestor and descendant, so the move is not a context
    switch. Treating it as one cleared ``space_bar_pressed`` between the Space
    press and the mouse press that needed it, so `Space` + click never reached
    the magnifier gesture (measured live 2026-10-22: ``[kbd-state] reset ...
    space=False`` on the mouse press, then only auto-repeat presses, which are
    rejected by design).

    A move to an unrelated widget (panel, flyout, another tab) or to no widget
    at all is NOT inside the context and must reset held keys.
    """
    if old_focus is None or new_focus is None:
        return False
    try:
        if old_focus is new_focus:
            return True
        return bool(old_focus.isAncestorOf(new_focus) or new_focus.isAncestorOf(old_focus))
    except Exception:
        return False

def _wname(w) -> str:
    if w is None:
        return "None"
    name = getattr(w, "objectName", lambda: "")() or ""
    cls = type(w).__name__
    return f"{cls}({name})" if name else cls


_KEY_NAMES = {
    Qt.Key.Key_Down: "Down", Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Space: "Space", Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Tab: "Tab",
}


def _key_name(key: int) -> str:
    return _KEY_NAMES.get(key, f"0x{key:X}")


def _widget_path(w) -> str:
    parts = []
    p = w
    while p is not None and len(parts) < 8:
        parts.append(type(p).__name__)
        p = p.parentWidget()
    return " → ".join(parts)


class EventHandler(QObject):
    drag_enter_event_signal = Signal(QDragEnterEvent)
    drag_move_event_signal = Signal(QDragMoveEvent)
    drag_leave_event_signal = Signal(QEvent)
    drop_event_signal = Signal(QDropEvent)
    resize_event_signal = Signal(QEvent)
    close_event_signal = Signal(QEvent)
    mouse_press_event_signal = Signal(QMouseEvent)
    mouse_release_event_signal = Signal(QMouseEvent)
    global_keyboard_press_event_signal = Signal(QKeyEvent)
    global_keyboard_release_event_signal = Signal(QKeyEvent)
    canvas_keyboard_press_event_signal = Signal(QKeyEvent)
    canvas_keyboard_release_event_signal = Signal(QKeyEvent)
    mouse_press_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_move_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_release_event_on_image_label_signal = Signal(QMouseEvent)
    mouse_wheel_event_on_image_label_signal = Signal(QWheelEvent)

    def __init__(self, store, presenter_ref):
        super().__init__()
        self.store = store
        self.presenter = presenter_ref
        # Mouse-press/release fan-out dedup: the same QMouseEvent is
        # delivered to every installEventFilter target (app + window +
        # image_label), so each physical press/release must emit once.
        # Dedup compares event *identity* (``is``) against the last emitted
        # event, held by strong reference so the object cannot be GC'd and
        # its address reused between deliveries — ``id()`` keys would
        # collide with a dead object after collection. The monotonic
        # sequence counters below tag each distinct physical press/release
        # (1, 2, 3, …) for trace/debug correlation; they are the dedup
        # generation, never an address.
        self._last_mouse_press_event = None
        self._last_mouse_press_seq = 0
        self._last_mouse_release_event = None
        self._last_mouse_release_seq = 0
        self._mouse_event_seq = 0
        self.runtime = build_event_handler_runtime(
            store,
            presenter_provider=lambda: self.presenter,
            parent=self,
        )
        self.interactive_movement = self.runtime.interactive_movement
        self.keyboard_handler = self.runtime.keyboard_handler
        self.keyboard_state = self.runtime.keyboard_state

        self.global_keyboard_press_event_signal.connect(self.handle_key_press)
        self.global_keyboard_release_event_signal.connect(self.handle_key_release)

    def eventFilter(self, watched_obj, event: QEvent) -> bool:
        event_type = event.type()

        # --- debug: structured key/focus trace ---
        watched_name = type(watched_obj).__name__ if watched_obj is not None else "None"
        if event_type == QEvent.Type.FocusIn:
            w = QApplication.focusWidget()
            logger.debug(
                "  FOCUS → %s (reason=%s) [via=%s]",
                _wname(w),
                event.reason().name if hasattr(event, "reason") else "?",
                watched_name,
            )
        elif event_type == QEvent.Type.FocusOut:
            logger.debug(
                "  FOCUS ← %s [via=%s]",
                _wname(watched_obj),
                watched_name,
            )
        elif event_type == QEvent.Type.KeyPress:
            w = QApplication.focusWidget()
            k = event.key()
            path = _widget_path(w) if w else "?"
            logger.debug(
                "  KEY %s(0x%X) → %s  path=%s [via=%s]",
                _key_name(k), k,
                _wname(w),
                path,
                watched_name,
            )
        # --- end debug ---

        dnd_service = DragAndDropService.get_instance()
        if route_drag_and_drop_override(self, event, dnd_service):
            return True

        # Close visible in-window ContextMenus on Escape before the global
        # keyboard handler consumes it — but only if no flyout section owns
        # the focused widget (flyout sections route Escape through
        # NavigationManager → extra_keys → keyPressEvent).
        if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            from sli_ui_toolkit.managers import NavigationManager
            if not NavigationManager.get_instance().should_intercept(Qt.Key.Key_Escape):
                from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import (
                    ContextMenu,
                )
                if ContextMenu.close_visible():
                    event.accept()
                    return True
                # A top-level-surface menu is a top-level WITHOUT focus, so it
                # never sees the Escape key itself and is not in the
                # toolkit's in-window registry. The app manager owns the
                # active one — close it here (2026-10-21).
                from ui.context_menu.manager import get_context_menu_manager
                if get_context_menu_manager().hide_active_menu():
                    event.accept()
                    return True

        if event_type == QEvent.Type.ApplicationDeactivate:
            self._reset_keyboard_state(f"event:{int(event_type)}")
        elif event_type == QEvent.Type.WindowDeactivate:
            app = QApplication.instance()
            active_window = app.activeWindow() if isinstance(app, QApplication) else None
            if watched_obj is self.presenter.main_window_app or watched_obj is active_window:
                self._reset_keyboard_state(f"event:{int(event_type)}")
        elif event_type == QEvent.Type.FocusOut:
            # Qt delivers FocusOut BEFORE the new focus owner is known, so the
            # decision is deferred one event-loop turn: a focus move inside the
            # same window (shell <-> canvas on every click) keeps held keys, a
            # move that really leaves the window resets them.
            self._schedule_focus_out_reset(watched_obj)

        if event_type == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            # Same QMouseEvent is delivered to every installEventFilter target
            # (app + window + image_label). Emit once per physical press:
            # identity against the pinned last event, tagged with the next
            # monotonic sequence number on first delivery.
            if event is not self._last_mouse_press_event:
                self._mouse_event_seq += 1
                self._last_mouse_press_event = event
                self._last_mouse_press_seq = self._mouse_event_seq
                self.mouse_press_event_signal.emit(event)
        elif event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event is not self._last_mouse_release_event:
                self._mouse_event_seq += 1
                self._last_mouse_release_event = event
                self._last_mouse_release_seq = self._mouse_event_seq
                self.mouse_release_event_signal.emit(event)

        if route_global_keyboard_event(self, watched_obj, event):
            return True

        if route_main_window_event(self, watched_obj, event, dnd_service):
            return True

        return super().eventFilter(watched_obj, event)

    def start_interactive_movement(self):
        self.interactive_movement.start()

    def stop_interactive_movement(self):
        self.interactive_movement.stop()

    def handle_key_press(self, event: QKeyEvent):
        self.keyboard_handler.handle_key_press(event)

    def handle_key_release(self, event: QKeyEvent):
        self.keyboard_handler.handle_key_release(event)

    def _schedule_focus_out_reset(self, watched_obj) -> None:
        """Decide a FocusOut reset once the new focus owner is known.

        Qt delivers FocusOut BEFORE the new owner exists, and it also delivers
        it for style objects, so the decision is made one event-loop turn later
        from the old/new *widgets*.

        The rule: a move between an ancestor and its descendant is the same
        focus context (the Image Compare click moves focus shell -> canvas ->
        shell, and that churn cleared ``space_bar_pressed`` between the Space
        press and the mouse press that needed it — measured live 2026-10-22).
        A move to an unrelated widget (panel, flyout, another tab) still resets.
        """
        app = QApplication.instance()
        old_focus = app.focusWidget() if isinstance(app, QApplication) else None
        if old_focus is None and isinstance(watched_obj, QWidget):
            old_focus = watched_obj
        generation = getattr(self, "_focus_out_generation", 0) + 1
        self._focus_out_generation = generation

        def _settle() -> None:
            if getattr(self, "_focus_out_generation", 0) != generation:
                return  # superseded by a newer FocusOut
            application = QApplication.instance()
            new_focus = (
                application.focusWidget()
                if isinstance(application, QApplication)
                else None
            )
            if not focus_move_stays_inside(old_focus, new_focus):
                self._reset_keyboard_state("focus-out:settled")

        QTimer.singleShot(0, _settle)

    def _reset_keyboard_state(self, reason: str) -> None:
        result = self.keyboard_state.reset()
        session_reset = False
        image_label_handler = getattr(self.presenter, "image_label_handler", None)
        if image_label_handler is not None:
            try:
                session_reset = image_label_handler.input_session.reset()
            except Exception:
                pass
        if not result.applied and not session_reset:
            return
        logger.debug(
            "[kbd-reset] reason=%s keyboard_reset=%s session_reset=%s",
            reason,
            result.applied,
            session_reset,
        )
        self.store.emit_viewport_change("interaction")
        if not session_reset:
            try:
                self.stop_interactive_movement()
            except Exception:
                pass