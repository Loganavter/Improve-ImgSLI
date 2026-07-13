from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

@runtime_checkable
class CanvasGeometryProvider(Protocol):
    """Structural capability for a tab's canvas widget: coordinate math and
    hit-testing that host-generic event routing needs (global keyboard
    routing, drag/drop, screen<->image coordinate conversion), without
    exposing the widget itself.

    A canvas-owning tab implements this once and returns an instance from
    ``TabContract.get_canvas_geometry_provider()``. Host code never receives
    the canvas widget — only these six primitive-returning queries. This is
    the single growth point for canvas-geometry needs: a new query is a new
    method here (and on the one provider implementation per canvas-owning
    tab), not a new method on ``TabContract`` that every tab, canvas or not,
    has to stub.
    """

    def owns_widget(self, candidate: Any) -> bool:
        """True if ``candidate`` is (or descends from) this tab's canvas."""
        ...

    def get_size(self) -> tuple[int, int] | None:
        """Canvas widget size in pixels, or ``None`` if not ready."""
        ...

    def map_global_to_local(self, global_pos: Any) -> Any | None:
        """Map a global (screen) ``QPoint`` into canvas-local coordinates."""
        ...

    def get_content_rect_px(self) -> tuple[int, int, int, int] | None:
        """Content rect in local pixels ``(x, y, w, h)`` — the area the
        image occupies inside the canvas, excluding letterboxing.
        """
        ...

    def get_zoom_pan(self) -> tuple[float, float, float]:
        """Current ``(zoom, pan_offset_x, pan_offset_y)``."""
        ...

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
