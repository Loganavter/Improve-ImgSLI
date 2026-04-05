from __future__ import annotations

from PyQt6.QtCore import QEvent

def _safe_getattr(obj, name: str, default=None):
    try:
        return getattr(obj, name, default)
    except RuntimeError:
        return default

def _is_canvas_event_target(event_handler, watched_obj) -> bool:
    presenter = event_handler.presenter
    if presenter is None or not hasattr(presenter, "ui"):
        return False
    image_label = _safe_getattr(presenter.ui, "image_label", None)
    if image_label is None:
        return False
    if watched_obj is image_label:
        return True
    if watched_obj is _safe_getattr(image_label, "_window_container", None):
        return True
    if watched_obj is _safe_getattr(image_label, "_canvas_window", None):
        return True
    return False

def route_main_window_event(event_handler, watched_obj, event: QEvent, dnd_service) -> bool:
    presenter = event_handler.presenter
    main_window = presenter.main_window_app if presenter else None
    is_main_window = watched_obj is main_window
    is_canvas_target = _is_canvas_event_target(event_handler, watched_obj)
    if not is_main_window and not is_canvas_target:
        return False

    event_type = event.type()
    if event_type == QEvent.Type.DragEnter:
        event_handler.drag_enter_event_signal.emit(event)
        return True
    if event_type == QEvent.Type.DragMove:
        event_handler.drag_move_event_signal.emit(event)
        return True
    if event_type == QEvent.Type.DragLeave:
        event_handler.drag_leave_event_signal.emit(event)
        return True
    if event_type == QEvent.Type.Drop:
        event_handler.drop_event_signal.emit(event)
        return True
    if event_type == QEvent.Type.Resize and is_main_window:
        event_handler.resize_timer.stop()
        event_handler.resize_timer.start(200)
        event_handler.resize_event_signal.emit(event)
        return False
    if event_type == QEvent.Type.Close and is_main_window:
        dnd_service.cancel_drag()
        event_handler.close_event_signal.emit(event)
        return False
    return False
