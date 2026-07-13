from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt

from tabs.registry import get_shared_tab_registry

logger = logging.getLogger("ImproveImgSLI")

def _belongs_to_canvas(event_handler, watched_obj) -> bool:
    tab = get_shared_tab_registry().get_active_tab()
    if tab is None:
        return False
    return tab.owns_widget(watched_obj)

def route_drag_and_drop_override(event_handler, event: QEvent, dnd_service) -> bool:
    event_type = event.type()
    if not dnd_service.is_dragging():
        return False
    if event_type == QEvent.Type.MouseMove:
        dnd_service.update_drag_position(event)
        return True
    if event_type == QEvent.Type.MouseButtonRelease:
        dnd_service.finish_drag(event)
        return True
    if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
        dnd_service.cancel_drag()
        return True
    if event_type in (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.Enter,
        QEvent.Type.Leave,
    ):
        return True
    return False

def route_global_keyboard_event(event_handler, watched_obj, event: QEvent) -> bool:
    event_type = event.type()
    if event_type not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        return False
    if _belongs_to_canvas(event_handler, watched_obj):
        if event_type == QEvent.Type.KeyPress:
            event_handler.canvas_keyboard_press_event_signal.emit(event)
        else:
            event_handler.canvas_keyboard_release_event_signal.emit(event)
        return True
    if not event_handler.keyboard_handler.should_route_globally(event, watched_obj):
        return False
    if event_type == QEvent.Type.KeyPress:
        event_handler.global_keyboard_press_event_signal.emit(event)
    else:
        event_handler.global_keyboard_release_event_signal.emit(event)
    return True
