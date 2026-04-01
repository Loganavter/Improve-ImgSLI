from __future__ import annotations

def get_main_controller(presenter):
    if presenter is None or not hasattr(presenter, "main_controller"):
        return None
    return presenter.main_controller

def get_event_bus(presenter):
    main_controller = get_main_controller(presenter)
    if main_controller is None:
        return None
    return getattr(main_controller, "event_bus", None)

def get_image_canvas_presenter(presenter):
    if presenter is None:
        return None
    if hasattr(presenter, "get_feature"):
        return presenter.get_feature("image_canvas")
    return None

def emit_update_request(presenter) -> None:
    main_controller = get_main_controller(presenter)
    if main_controller is not None:
        main_controller.update_requested.emit()

def schedule_image_canvas_update(presenter) -> None:
    image_canvas_presenter = get_image_canvas_presenter(presenter)
    if image_canvas_presenter is not None:
        image_canvas_presenter.schedule_update()

def clear_presenter_render_snapshots(presenter) -> None:
    if presenter is None:
        return
    if hasattr(presenter, "_last_store_snapshot"):
        delattr(presenter, "_last_store_snapshot")
    if hasattr(presenter, "_last_render_params_dict"):
        delattr(presenter, "_last_render_params_dict")
