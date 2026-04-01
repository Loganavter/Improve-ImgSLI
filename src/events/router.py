from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt

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
    if not event_handler.keyboard_handler.should_route_globally(event, watched_obj):
        return False
    if event_type == QEvent.Type.KeyPress:
        event_handler.keyboard_press_event_signal.emit(event)
    else:
        event_handler.keyboard_release_event_signal.emit(event)
    return True
