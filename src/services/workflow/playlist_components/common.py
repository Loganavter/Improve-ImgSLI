from __future__ import annotations

from core.events import ComparisonUIUpdateEvent

def get_presenter(main_controller):
    if main_controller and getattr(main_controller, "window_shell", None):
        return main_controller.window_shell
    return None

def get_target_list(store, image_number: int):
    return store.document.image_list1 if image_number == 1 else store.document.image_list2

def get_current_index(store, image_number: int) -> int:
    return (
        store.document.current_index1
        if image_number == 1
        else store.document.current_index2
    )

def set_current_index(store, image_number: int, index: int) -> None:
    if image_number == 1:
        store.document.current_index1 = index
    else:
        store.document.current_index2 = index

def get_current_item_path(store, image_number: int):
    target_list = get_target_list(store, image_number)
    current_index = get_current_index(store, image_number)
    if 0 <= current_index < len(target_list):
        return target_list[current_index].path
    return None

def find_index_by_path(items, path):
    if not path:
        return -1
    try:
        return next(i for i, item in enumerate(items) if item.path == path)
    except StopIteration:
        return -1

def emit_ui_update(main_controller, payload) -> None:
    if not main_controller:
        return

    ui_signal = getattr(main_controller, "ui_update_requested", None)
    if ui_signal is not None:
        ui_signal.emit(list(payload))
        return

    event_bus = getattr(main_controller, "event_bus", None)
    if event_bus is None:
        plugin = getattr(main_controller, "plugin", None)
        event_bus = getattr(plugin, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ComparisonUIUpdateEvent(components=tuple(payload)))
