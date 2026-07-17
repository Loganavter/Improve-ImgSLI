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


def compute_main_window_minimum(main_window) -> tuple[int, int]:
    if not getattr(main_window, "_is_ui_stable", False):
        return (
            MAIN_WINDOW_MIN_WIDTH_FLOOR + MAIN_WINDOW_MIN_PADDING_PX,
            MAIN_WINDOW_MIN_HEIGHT_FLOOR + MAIN_WINDOW_MIN_PADDING_PX,
        )
    canvas, layout = _resolve_canvas(main_window)
    return measure_layout_minimum_with_preferred_canvas(
        layout,
        canvas,
        min_width_floor=MAIN_WINDOW_MIN_WIDTH_FLOOR,
        min_height_floor=MAIN_WINDOW_MIN_HEIGHT_FLOOR,
        padding=MAIN_WINDOW_MIN_PADDING_PX,
    )


def apply_main_window_minimum(main_window) -> None:
    width, height = compute_main_window_minimum(main_window)
    apply_dialog_geometry(
        main_window,
        width,
        height,
        policy=MAIN_WINDOW_GEOMETRY_POLICY,
    )
