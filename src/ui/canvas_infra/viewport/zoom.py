from __future__ import annotations

from ui.canvas_infra.viewport.contract import (
    CanvasViewportFeature,
    DisplaySplitPositionRequest,
    PanDragRequest,
    SplitPositionForViewTransformRequest,
    WheelZoomRequest,
)
from ui.canvas_infra.viewport.geometry import QuickContentRect, resolve_axis_position

def _resolve_content_rect(
    *,
    request_content_rect: QuickContentRect | None,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
) -> QuickContentRect | None:
    """Every real call site now resolves and passes an explicit
    ``content_rect`` (sourced from ``_inner_content_rect_px``/
    ``_content_rect_px``, already feature-padding-aware — see
    docs/dev/QRHI_CANVAS_FEATURES.md). This is only a defensive
    fallback for a caller that hasn't resolved one yet; it deliberately does
    *not* know about virtual-canvas padding — a caller needing padding-aware
    geometry must call ``resolve_canvas_content_geometry`` itself and pass
    the result in, not rely on this bare letterbox fit."""
    if request_content_rect is not None:
        return request_content_rect
    if widget_width <= 0 or widget_height <= 0 or image_width <= 0 or image_height <= 0:
        return None
    ratio = min(widget_width / image_width, widget_height / image_height)
    content_width = max(1.0, image_width * ratio)
    content_height = max(1.0, image_height * ratio)
    return QuickContentRect(
        x=(widget_width - content_width) / 2.0,
        y=(widget_height - content_height) / 2.0,
        width=content_width,
        height=content_height,
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
        base = resolve_axis_position(
            content_rect.y, content_rect.height, request.split_visual
        ) / max(1.0, float(request.widget_height))
        pan = float(request.pan_offset_y)
    else:
        base = resolve_axis_position(
            content_rect.x, content_rect.width, request.split_visual
        ) / max(1.0, float(request.widget_width))
        pan = float(request.pan_offset_x)

    result = (base - 0.5 + pan) * float(request.zoom_level) + 0.5
    # Do not clamp to ``[0, 1]``: when zoomed out / panned the content spit
    # can leave the widget, and clamping glued the divider to the screen edge
    # ("flies with the camera") while the image kept moving — worst on the
    # spit axis that hits the clamp first (often Y with letterboxed height).
    return result

def compute_zoom_split_position_for_view_transform(
    request: SplitPositionForViewTransformRequest,
) -> float | None:
    """Dual-mode spit ownership along the comparison axis.

    - ``zoom <= 1``: content-anchored — store spit stays put; the line/seam
      ride with the image via display / letterboxed-UV math.
    - ``zoom > 1``: camera-anchored — rewrite content spit so the **screen**
      spit stays fixed while pan/zoom change (inspect / crop workflow).

    Always clamp the rewritten value to content ``[0, 1]``. Returning
    ``None`` means "leave store unchanged."
    """
    if (
        request.image_width <= 0
        or request.image_height <= 0
        or request.widget_width <= 0
        or request.widget_height <= 0
    ):
        return None

    if float(request.new_zoom) <= 1.0:
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
        base = resolve_axis_position(
            content_rect.y, content_rect.height, request.split_position_visual
        ) / max(1.0, float(request.widget_height))
        old_pan = float(request.current_pan_y)
        new_pan = float(request.new_pan_y)
        axis_widget_size = float(request.widget_height)
        axis_content_offset = float(content_rect.y)
        axis_content_size = float(content_rect.height)
    else:
        base = resolve_axis_position(
            content_rect.x, content_rect.width, request.split_position_visual
        ) / max(1.0, float(request.widget_width))
        old_pan = float(request.current_pan_x)
        new_pan = float(request.new_pan_x)
        axis_widget_size = float(request.widget_width)
        axis_content_offset = float(content_rect.x)
        axis_content_size = float(content_rect.width)

    # Hold the current screen spit fixed across the camera change, then
    # invert back into content spit for the new pan/zoom.
    screen_pos = (base - 0.5 + old_pan) * float(request.current_zoom) + 0.5
    new_base = (
        (screen_pos - 0.5) / max(float(request.new_zoom), 1e-6) + 0.5 - new_pan
    )
    new_split = (
        (new_base * axis_widget_size) - axis_content_offset
    ) / max(axis_content_size, 1.0)
    return max(0.0, min(1.0, new_split))

def compute_zoom_wheel_transform(request: WheelZoomRequest) -> tuple[float, float, float] | None:
    factor = 1.1 if int(request.angle_delta_y) > 0 else 0.9
    new_zoom = max(0.1, min(float(request.current_zoom) * factor, 50.0))
    if abs(new_zoom - float(request.current_zoom)) <= 1e-6:
        return None

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
