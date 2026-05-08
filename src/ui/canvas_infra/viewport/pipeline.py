from __future__ import annotations

from .contract import (
    DisplaySplitPositionRequest,
    PanDragRequest,
    SplitPositionForViewTransformRequest,
    WheelZoomRequest,
)
from .registry import get_canvas_viewport_features

def compute_display_split_position(request: DisplaySplitPositionRequest) -> float:
    for feature in sorted(get_canvas_viewport_features(), key=lambda item: (item.order, item.name)):
        result = feature.compute_display_split_position(request)
        if result is not None:
            return float(result)
    return max(0.0, min(1.0, float(request.split_visual)))

def compute_split_position_for_view_transform(
    request: SplitPositionForViewTransformRequest,
) -> float | None:
    for feature in sorted(get_canvas_viewport_features(), key=lambda item: (item.order, item.name)):
        result = feature.compute_split_position_for_view_transform(request)
        if result is not None:
            return float(result)
    return None

def compute_wheel_zoom_transform(request: WheelZoomRequest) -> tuple[float, float, float] | None:
    for feature in sorted(get_canvas_viewport_features(), key=lambda item: (item.order, item.name)):
        result = feature.compute_wheel_zoom_transform(request)
        if result is not None:
            new_zoom, new_pan_x, new_pan_y = result
            return float(new_zoom), float(new_pan_x), float(new_pan_y)
    return None

def compute_pan_drag_transform(request: PanDragRequest) -> tuple[float, float] | None:
    for feature in sorted(get_canvas_viewport_features(), key=lambda item: (item.order, item.name)):
        result = feature.compute_pan_drag_transform(request)
        if result is not None:
            new_pan_x, new_pan_y = result
            return float(new_pan_x), float(new_pan_y)
    return None
