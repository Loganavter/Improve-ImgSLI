from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import (
    QMouseEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication
from events.app_event import (
    route_main_window_event,
)
from events.drag_drop_handler import DragAndDropService
from events.router import route_drag_and_drop_override, route_global_keyboard_event
from events.runtime import build_event_handler_runtime

import logging

logger = logging.getLogger("ImproveImgSLI")


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
        # keyboard handler consumes it.
        if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import (
                ContextMenu,
            )
            if ContextMenu.close_visible():
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
            if watched_obj is self.presenter.main_window_app:
                self._reset_keyboard_state(f"event:{int(event_type)}")

        if event_type == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            # Same QMouseEvent is delivered to every installEventFilter target
            # (app + window + image_label). Emit once per physical press.
            press_key = (id(event), event.button(), event.timestamp())
            if press_key != getattr(self, "_last_mouse_press_key", None):
                self._last_mouse_press_key = press_key
                self.mouse_press_event_signal.emit(event)
        elif event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            release_key = (id(event), event.button(), event.timestamp())
            if release_key != getattr(self, "_last_mouse_release_key", None):
                self._last_mouse_release_key = release_key
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