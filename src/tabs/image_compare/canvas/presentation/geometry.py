from __future__ import annotations

from dataclasses import dataclass

from shared.rendering import VirtualCanvasLayout
from ui.canvas_infra.scene.layout_requirements import resolve_feature_virtual_layout

@dataclass(frozen=True)
class CanvasGeometry:
    image_width: int
    image_height: int
    canvas_width: int
    canvas_height: int
    padding_left: int
    padding_top: int
    padding_right: int
    padding_bottom: int
    virtual_layout: VirtualCanvasLayout | None = None

class _FallbackGuidesState:
    enabled = False
    thickness = 1
    color = type("C", (), {"r": 255, "g": 255, "b": 255, "a": 255})()

def _resolve_overlay_virtual_layout(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> VirtualCanvasLayout | None:
    return resolve_feature_virtual_layout(
        store,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
    )

def _resolve_overlay_padding(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> tuple[tuple[int, int, int, int], VirtualCanvasLayout | None]:
    layout = _resolve_overlay_virtual_layout(
        store,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
    )
    if layout is None:
        return (0, 0, 0, 0), None
    padding = layout.resolve_padding_pixels(
        base_width=drawing_width,
        base_height=drawing_height,
    )
    return (
        padding,
        layout,
    )

def compute_canvas_plan(
    store,
    image_width: int,
    image_height: int,
) -> CanvasGeometry:
    padding, virtual_layout = _resolve_overlay_padding(
        store,
        drawing_width=image_width,
        drawing_height=image_height,
    )
    pad_left, pad_right, pad_top, pad_bottom = padding
    return CanvasGeometry(
        image_width=image_width,
        image_height=image_height,
        canvas_width=image_width + pad_left + pad_right,
        canvas_height=image_height + pad_top + pad_bottom,
        padding_left=pad_left,
        padding_top=pad_top,
        padding_right=pad_right,
        padding_bottom=pad_bottom,
        virtual_layout=virtual_layout,
    )

