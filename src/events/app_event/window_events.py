from __future__ import annotations

from PyQt6.QtCore import QEvent

def route_main_window_event(event_handler, watched_obj, event: QEvent, dnd_service) -> bool:
    presenter = event_handler.presenter
    main_window = presenter.main_window_app if presenter else None
    if watched_obj is not main_window:
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
    if event_type == QEvent.Type.Resize:
        event_handler.resize_timer.stop()
        event_handler.resize_timer.start(200)
        event_handler.resize_event_signal.emit(event)
        return False
    if event_type == QEvent.Type.Close:
        dnd_service.cancel_drag()
        event_handler.close_event_signal.emit(event)
        return False
    return False
