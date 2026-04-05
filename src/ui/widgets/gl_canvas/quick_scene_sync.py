from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QColor

from .quick_bridge import QuickCanvasBridge
from .quick_geometry import build_content_rect

def _float_attr(obj, attr: str, default: float) -> float:
    if obj is None:
        return float(default)
    value = getattr(obj, attr, None)
    if value is None:
        return float(default)
    return float(value)

@dataclass(frozen=True)
class QuickSceneSignature:
    split_visual: float
    is_horizontal: bool
    show_divider: bool
    divider_thickness: int
    render_magnifiers: bool

def scene_signature(scene, fallback_split: float, fallback_horizontal: bool) -> QuickSceneSignature | None:
    if scene is None:
        return None
    return QuickSceneSignature(
        split_visual=_float_attr(scene, "split_position_visual", fallback_split),
        is_horizontal=bool(getattr(scene, "is_horizontal", fallback_horizontal)),
        show_divider=bool(getattr(scene, "show_divider", False)),
        divider_thickness=int(getattr(scene, "divider_thickness", 0) or 0),
        render_magnifiers=bool(getattr(scene, "render_magnifiers", False)),
    )

def apply_scene_to_bridge(
    *,
    bridge: QuickCanvasBridge,
    scene,
    image_width: int,
    image_height: int,
    widget_width: int,
    widget_height: int,
    zoom_level: float,
    pan_offset_x: float,
    pan_offset_y: float,
) -> tuple[bool, float]:
    is_horizontal = bool(getattr(scene, "is_horizontal", False))
    split_visual = _float_attr(scene, "split_position_visual", 0.5)
    content_rect = build_content_rect(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=image_width,
        image_height=image_height,
    )
    bridge.set_is_horizontal(is_horizontal)
    bridge.set_split_position(split_visual)
    bridge.set_show_divider(bool(getattr(scene, "show_divider", False)))
    bridge.set_divider_color(
        QColor(getattr(scene, "divider_color", QColor(255, 255, 255, 255)))
    )
    bridge.set_divider_thickness(
        float(max(1, int(getattr(scene, "divider_thickness", 2) or 2)))
    )
    if content_rect is None:
        bridge.set_content_x(0.0)
        bridge.set_content_y(0.0)
        bridge.set_content_width(float(widget_width))
        bridge.set_content_height(float(widget_height))
    else:
        bridge.set_content_x(float(content_rect.x))
        bridge.set_content_y(float(content_rect.y))
        bridge.set_content_width(float(content_rect.width))
        bridge.set_content_height(float(content_rect.height))
        if split_visual <= 0.01 or split_visual >= 0.99:
            import logging

            logging.getLogger("ImproveImgSLI").debug(
                "Quick scene content edge | split=%.4f content=(%.1f, %.1f, %.1f, %.1f) widget=%sx%s image=%sx%s",
                split_visual,
                float(content_rect.x),
                float(content_rect.y),
                float(content_rect.width),
                float(content_rect.height),
                int(widget_width),
                int(widget_height),
                int(image_width),
                int(image_height),
            )
    return is_horizontal, split_visual
