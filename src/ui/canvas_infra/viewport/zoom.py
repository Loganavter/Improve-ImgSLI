from __future__ import annotations

from ui.canvas_infra.viewport.contract import (
    CanvasViewportFeature,
    DisplaySplitPositionRequest,
    PanDragRequest,
    SplitPositionForViewTransformRequest,
    WheelZoomRequest,
)
from ui.canvas_infra.viewport.geometry import QuickContentRect, build_content_rect

def _resolve_content_rect(
    *,
    request_content_rect: QuickContentRect | None,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
) -> QuickContentRect | None:
    if request_content_rect is not None:
        return request_content_rect
    return build_content_rect(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=image_width,
        image_height=image_height,
    )

def compute_zoom_display_split_position(request: DisplaySplitPositionRequest) -> float | None:
    content_rect = _resolve_content_rect(
        request_content_rect=request.content_rect,
        widget_width=request.widget_width,
        widget_height=request.widget_height,
        image_width=request.image_width,
        image_height=request.image_height,
    )
    if content_rect is None:
        return max(0.0, min(1.0, float(request.split_visual)))

    if request.is_horizontal:
        base = (
            content_rect.y + (content_rect.height * float(request.split_visual))
        ) / max(1.0, float(request.widget_height))
        pan = float(request.pan_offset_y)
    else:
        base = (
            content_rect.x + (content_rect.width * float(request.split_visual))
        ) / max(1.0, float(request.widget_width))
        pan = float(request.pan_offset_x)

    if float(request.zoom_level) <= 1.0:
        pan = 0.0

    return max(
        0.0,
        min(1.0, (base - 0.5 + pan) * float(request.zoom_level) + 0.5),
    )

def compute_zoom_split_position_for_view_transform(
    request: SplitPositionForViewTransformRequest,
) -> float | None:
    if (
        request.image_width <= 0
        or request.image_height <= 0
        or request.widget_width <= 0
        or request.widget_height <= 0
    ):
        return None

    content_rect = _resolve_content_rect(
        request_content_rect=request.content_rect,
        widget_width=request.widget_width,
        widget_height=request.widget_height,
        image_width=request.image_width,
        image_height=request.image_height,
    )
    if content_rect is None:
        return None

    if request.is_horizontal:
        base = (
            content_rect.y + content_rect.height * float(request.split_position_visual)
        ) / max(1.0, float(request.widget_height))
        old_pan = float(request.current_pan_y)
    else:
        base = (
            content_rect.x + content_rect.width * float(request.split_position_visual)
        ) / max(1.0, float(request.widget_width))
        old_pan = float(request.current_pan_x)

    axis_widget_size = float(request.widget_height if request.is_horizontal else request.widget_width)
    axis_content_size = float(content_rect.height if request.is_horizontal else content_rect.width)
    axis_content_offset = float(content_rect.y if request.is_horizontal else content_rect.x)
    current_pan = float(request.current_pan_y if request.is_horizontal else request.current_pan_x)
    new_pan = float(request.new_pan_y if request.is_horizontal else request.new_pan_x)
    if float(request.current_zoom) <= 1.0:
        old_pan = 0.0
        current_pan = 0.0
    if float(request.new_zoom) <= 1.0:
        new_pan = 0.0

    def _visible_axis_range(zoom: float, pan: float) -> tuple[float, float]:
        local_start = ((0.0 - 0.5) / max(float(zoom), 1e-6)) + 0.5 - pan
        local_end = ((1.0 - 0.5) / max(float(zoom), 1e-6)) + 0.5 - pan
        rel_start = ((local_start * axis_widget_size) - axis_content_offset) / max(axis_content_size, 1.0)
        rel_end = ((local_end * axis_widget_size) - axis_content_offset) / max(axis_content_size, 1.0)
        lo = max(0.0, min(1.0, min(rel_start, rel_end)))
        hi = max(0.0, min(1.0, max(rel_start, rel_end)))
        return lo, hi

    explicit_edge_epsilon = 1e-6
    if request.split_position_visual <= explicit_edge_epsilon:
        new_visible_min, _ = _visible_axis_range(request.new_zoom, new_pan)
        return max(0.0, min(1.0, new_visible_min))
    if request.split_position_visual >= 1.0 - explicit_edge_epsilon:
        _, new_visible_max = _visible_axis_range(request.new_zoom, new_pan)
        return max(0.0, min(1.0, new_visible_max))

    if float(request.new_zoom) <= 1.0:
        return float(request.split_position_visual)

    screen_pos = (base - 0.5 + old_pan) * float(request.current_zoom) + 0.5
    new_base = (screen_pos - 0.5) / max(float(request.new_zoom), 1e-6) + 0.5 - new_pan

    if request.is_horizontal:
        new_split = (
            (new_base * float(request.widget_height) - content_rect.y) / max(content_rect.height, 1.0)
        )
    else:
        new_split = (
            (new_base * float(request.widget_width) - content_rect.x) / max(content_rect.width, 1.0)
        )

    return max(0.0, min(1.0, new_split))

def compute_zoom_wheel_transform(request: WheelZoomRequest) -> tuple[float, float, float] | None:
    factor = 1.1 if int(request.angle_delta_y) > 0 else 0.9
    new_zoom = max(0.1, min(float(request.current_zoom) * factor, 50.0))
    if abs(new_zoom - float(request.current_zoom)) <= 1e-6:
        return None

    if new_zoom <= 1.0:
        return new_zoom, 0.0, 0.0

    new_pan_x = float(request.current_pan_x)
    new_pan_y = float(request.current_pan_y)
    if request.widget_width > 0 and request.widget_height > 0:
        mx = float(request.mouse_x) / float(request.widget_width)
        my = float(request.mouse_y) / float(request.widget_height)
        uv_x = (mx - 0.5) / max(float(request.current_zoom), 1e-6) + 0.5 - float(request.current_pan_x)
        uv_y = (my - 0.5) / max(float(request.current_zoom), 1e-6) + 0.5 - float(request.current_pan_y)
        uv_x = max(0.0, min(1.0, uv_x))
        uv_y = max(0.0, min(1.0, uv_y))
        new_pan_x = 0.5 - uv_x + (mx - 0.5) / new_zoom
        new_pan_y = 0.5 - uv_y + (my - 0.5) / new_zoom

    return new_zoom, new_pan_x, new_pan_y

def compute_zoom_pan_drag_transform(request: PanDragRequest) -> tuple[float, float] | None:
    if request.widget_width <= 0 or request.widget_height <= 0:
        return None

    if float(request.current_zoom) <= 1.0:
        return 0.0, 0.0
    dx = (float(request.mouse_x) - float(request.last_mouse_x)) / (
        float(request.widget_width) * max(float(request.current_zoom), 1e-6)
    )
    dy = (float(request.mouse_y) - float(request.last_mouse_y)) / (
        float(request.widget_height) * max(float(request.current_zoom), 1e-6)
    )
    return float(request.current_pan_x) + dx, float(request.current_pan_y) + dy

VIEWPORT_FEATURE = CanvasViewportFeature(
    name="zoom",
    compute_display_split_position=compute_zoom_display_split_position,
    compute_split_position_for_view_transform=compute_zoom_split_position_for_view_transform,
    compute_wheel_zoom_transform=compute_zoom_wheel_transform,
    compute_pan_drag_transform=compute_zoom_pan_drag_transform,
    order=100,
)
