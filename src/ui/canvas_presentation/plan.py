from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class CaptureCircle:
    center: object
    radius: float
    color: object

@dataclass(frozen=True)
class GuideSet:
    capture_center: object
    capture_radius: float
    target_centers: tuple[object, ...]
    target_radii: tuple[float, ...]
    color: object

@dataclass(frozen=True)
class OverlaySlot:
    center: object
    radius: float
    uv_rect: tuple[float, float, float, float]
    uv_rect2: tuple[float, float, float, float]
    source: int
    is_combined: bool
    internal_split: float
    horizontal: bool
    divider_visible: bool
    divider_color: tuple[float, float, float, float]
    divider_thickness_uv: float
    border_color: object
    border_width: float

@dataclass(frozen=True)
class OverlayLayout:
    slots: tuple[OverlaySlot, ...] = field(default_factory=tuple)
    capture_circles: tuple[CaptureCircle, ...] = field(default_factory=tuple)
    guide_sets: tuple[GuideSet, ...] = field(default_factory=tuple)
    capture_center: object | None = None
    capture_radius: float = 0.0
    magnifier_centers: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    mag_radius: float = 0.0
    border_color: object | None = None
    border_width: float = 2.0
    channel_mode: int = 0
    diff_mode: int = 0
    interp_mode: int = 1

MagnifierSlot = OverlaySlot
MagnifierLayout = OverlayLayout

@dataclass(frozen=True)
class CanvasRenderPlan:
    """
    Immutable frame descriptor — everything needed to render one GL canvas frame.

    ``canvas_w`` × ``canvas_h`` are the dimensions of the uploaded image pair.
    Feature-owned overlay geometry is stored in canvas-px and converted to
    widget-px only inside the shared runtime-overlay applicator.
    """

    image1: object
    image2: object
    source_image1: object
    source_image2: object
    source_key: tuple
    canvas_w: int
    canvas_h: int
    gl_scene: object
    overlay_layout: OverlayLayout | None
    capture_visible: bool
    capture_color: object
    guides_enabled: bool
    guides_color: object
    guides_thickness: int
    display_cache_key: tuple | None = None
    output_scale: float = 1.0
    preserve_zoom: bool = False
