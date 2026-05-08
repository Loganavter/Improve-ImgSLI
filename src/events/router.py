from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, Qt

logger = logging.getLogger("ImproveImgSLI")

def _is_same_object_or_descendant(candidate, target) -> bool:
    current = candidate
    while current is not None:
        if current is target:
            return True
        current = current.parent()
    return False

def _belongs_to_canvas(event_handler, watched_obj) -> bool:
    presenter = getattr(event_handler, "presenter", None)
    if presenter is None or getattr(presenter, "ui", None) is None:
        return False
    image_label = getattr(presenter.ui, "image_label", None)
    if image_label is None:
        return False
    if _is_same_object_or_descendant(watched_obj, image_label):
        return True
    for attr_name in ("_window_container", "_canvas_window"):
        owned = getattr(image_label, attr_name, None)
        if watched_obj is owned or _is_same_object_or_descendant(watched_obj, owned):
            return True
    return False

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
