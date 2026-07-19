"""Per-frame render context for the Multi Compare scene."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectedLayer:
    """One composition layer projected for a frame.

    ``rect_fb`` stays in framebuffer pixels for CPU overlays (labels,
    dividers). Image draws use ``slot_rect_uv`` + context letterbox in the
    fragment shader on a fullscreen quad — not per-slot NDC vertices.
    """

    layer: object
    slot_id: int
    rect_fb: tuple[float, float, float, float]
    slot_rect_uv: tuple[float, float, float, float]
    fit_x: float
    fit_y: float
    zoom: float
    pan_x: float
    pan_y: float


@dataclass(frozen=True, slots=True)
class MultiCompareRenderContext:
    """Immutable frame data shared by all local render passes."""

    composition: object | None
    framebuffer_size: tuple[float, float]
    scale: float
    offset: tuple[float, float]
    clip_matrix: tuple[float, ...]
    projected_layers: tuple[ProjectedLayer, ...]
    widget: object | None = None
