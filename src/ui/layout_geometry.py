"""Main window content-driven minimum size."""

from __future__ import annotations

from shared_toolkit.ui.layout_sizing import (
    GeometryApplyPolicy,
    apply_dialog_geometry,
    measure_layout_minimum_with_preferred_canvas,
)

MAIN_WINDOW_MIN_WIDTH_FLOOR = 250
MAIN_WINDOW_MIN_HEIGHT_FLOOR = 300
MAIN_WINDOW_MIN_PADDING_PX = 10

MAIN_WINDOW_GEOMETRY_POLICY = GeometryApplyPolicy(
    resize_when_hidden=False,
    update_minimum=True,
    minimum_floor=(MAIN_WINDOW_MIN_WIDTH_FLOOR, MAIN_WINDOW_MIN_HEIGHT_FLOOR),
    width_bounds=None,
    center_on_parent=False,
)


def _resolve_canvas(main_window):
    presenter = getattr(main_window, "presenter", None)
    if presenter is None:
        return None, None
    image_canvas = presenter.get_feature("image_canvas")
    if image_canvas is None:
        return None, main_window.layout()
    from tabs.image_compare.canvas.helpers import get_canvas

    widget = getattr(image_canvas, "widget", None)
    return get_canvas(widget), main_window.layout()


def _active_workspace_page(main_window):
    ui = getattr(main_window, "ui", None)
    stack = getattr(ui, "workspace_stack", None) if ui is not None else None
    if stack is None:
        return None
    return stack.currentWidget()


def minimum_floor_for_main_window(main_window) -> tuple[int, int]:
    """Base floor, raised by the active workspace page when it declares one."""
    floor_w = MAIN_WINDOW_MIN_WIDTH_FLOOR
    floor_h = MAIN_WINDOW_MIN_HEIGHT_FLOOR
    page = _active_workspace_page(main_window)
    if page is None:
        return floor_w, floor_h
    window_min = getattr(page, "window_minimum_size", None)
    if callable(window_min):
        try:
            width, height = window_min()
        except Exception:
            return floor_w, floor_h
        return max(floor_w, int(width)), max(floor_h, int(height))
    return (
        max(floor_w, int(page.minimumWidth())),
        max(floor_h, int(page.minimumHeight())),
    )


def compute_main_window_minimum(main_window) -> tuple[int, int]:
    floor_w, floor_h = minimum_floor_for_main_window(main_window)
    if not getattr(main_window, "_is_ui_stable", False):
        return (
            floor_w + MAIN_WINDOW_MIN_PADDING_PX,
            floor_h + MAIN_WINDOW_MIN_PADDING_PX,
        )
    canvas, layout = _resolve_canvas(main_window)
    return measure_layout_minimum_with_preferred_canvas(
        layout,
        canvas,
        min_width_floor=floor_w,
        min_height_floor=floor_h,
        padding=MAIN_WINDOW_MIN_PADDING_PX,
    )


def apply_main_window_minimum(main_window) -> None:
    width, height = compute_main_window_minimum(main_window)
    floor = minimum_floor_for_main_window(main_window)
    policy = GeometryApplyPolicy(
        resize_when_hidden=MAIN_WINDOW_GEOMETRY_POLICY.resize_when_hidden,
        update_minimum=MAIN_WINDOW_GEOMETRY_POLICY.update_minimum,
        minimum_floor=floor,
        width_bounds=MAIN_WINDOW_GEOMETRY_POLICY.width_bounds,
        center_on_parent=MAIN_WINDOW_GEOMETRY_POLICY.center_on_parent,
        lock_minimum_to_computed=MAIN_WINDOW_GEOMETRY_POLICY.lock_minimum_to_computed,
        force_resize=MAIN_WINDOW_GEOMETRY_POLICY.force_resize,
    )
    apply_dialog_geometry(
        main_window,
        width,
        height,
        policy=policy,
    )
