from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True, slots=True)
class DisplaySplitPositionRequest:
    widget_width: int
    widget_height: int
    image_width: int
    image_height: int
    split_visual: float
    is_horizontal: bool
    zoom_level: float
    pan_offset_x: float
    pan_offset_y: float
    content_rect: Any | None = None

@dataclass(frozen=True, slots=True)
class SplitPositionForViewTransformRequest:
    widget_width: int
    widget_height: int
    image_width: int
    image_height: int
    is_horizontal: bool
    split_position_visual: float
    current_zoom: float
    current_pan_x: float
    current_pan_y: float
    new_zoom: float
    new_pan_x: float
    new_pan_y: float
    content_rect: Any | None = None

ComputeDisplaySplitPositionFn = Callable[[DisplaySplitPositionRequest], float | None]
ComputeSplitPositionForViewTransformFn = Callable[[SplitPositionForViewTransformRequest], float | None]

@dataclass(frozen=True, slots=True)
class WheelZoomRequest:
    widget_width: int
    widget_height: int
    mouse_x: float
    mouse_y: float
    current_zoom: float
    current_pan_x: float
    current_pan_y: float
    angle_delta_y: int

@dataclass(frozen=True, slots=True)
class PanDragRequest:
    widget_width: int
    widget_height: int
    current_zoom: float
    current_pan_x: float
    current_pan_y: float
    last_mouse_x: float
    last_mouse_y: float
    mouse_x: float
    mouse_y: float

ComputeWheelZoomTransformFn = Callable[[WheelZoomRequest], tuple[float, float, float] | None]
ComputePanDragTransformFn = Callable[[PanDragRequest], tuple[float, float] | None]

@dataclass(frozen=True, slots=True)
class CanvasViewportFeature:
    name: str
    compute_display_split_position: ComputeDisplaySplitPositionFn
    compute_split_position_for_view_transform: ComputeSplitPositionForViewTransformFn
    compute_wheel_zoom_transform: ComputeWheelZoomTransformFn
    compute_pan_drag_transform: ComputePanDragTransformFn
    order: int = 100
