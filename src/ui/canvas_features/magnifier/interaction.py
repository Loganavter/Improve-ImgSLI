"""Magnifier-side interaction helpers.

These functions own the geometry math for magnifier drags and hit-testing.
They live inside the magnifier package because the math is specific to
overlay circles, capture rect, and internal-split logic — shared geometry
helpers stay neutral in ``events/image_label/geometry.py``.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF

from domain.types import Point
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

def _scene_compare_pos(handler, pos: QPointF, use_internal_coords: bool = True) -> Point:
    return handler.geometry.get_scene_compare_pos(pos, use_internal_coords=use_internal_coords)

def _get_canvas_scene(handler):
    label = handler.geometry._get_image_label()
    state = getattr(label, "runtime_state", None) if label is not None else None
    return getattr(state, "_canvas_scene_graph", None) if state is not None else None

def overlay_geometry_at(
    handler, pos: QPointF, use_internal_coords: bool = True
) -> tuple[Point, float] | None:
    compare_pos = _scene_compare_pos(handler, pos, use_internal_coords)
    scene = _get_canvas_scene(handler)
    if scene is None:
        return None
    from ui.canvas_infra.scene.hit_test import find_scene_object_at_position
    scene_object = find_scene_object_at_position(scene, compare_pos)
    if scene_object is None:
        return None
    circle = scene_object.interactive_circle()
    if circle is None:
        return None
    return circle.center, circle.radius

def is_point_in_overlay(handler, pos: QPointF, use_internal_coords: bool = True) -> bool:
    return overlay_geometry_at(handler, pos, use_internal_coords=use_internal_coords) is not None

def pick_overlay_at(
    handler, position: QPointF, use_internal_coords: bool = True
) -> str | None:
    compare_pos = _scene_compare_pos(handler, position, use_internal_coords)
    scene = _get_canvas_scene(handler)
    if scene is None:
        return None
    from ui.canvas_infra.scene.hit_test import find_scene_object_at_position
    match = find_scene_object_at_position(scene, compare_pos)
    if match is not None:
        set_active = get_canvas_feature_command_by_alias("overlay.set_active_instance")
        if set_active is not None:
            set_active(handler.store, match.id)
    return match.id if match is not None else None

def apply_capture_drag(handler, cursor_pos: QPointF) -> None:
    """Update overlay position from a cursor drag (overlay-mode branch)."""
    raw_rel_x, raw_rel_y = handler.geometry.screen_to_image_rel(
        cursor_pos, clamp=False, ignore_pan=False,
    )
    if raw_rel_x is None:
        return
    position = Point(float(raw_rel_x), float(raw_rel_y))
    command = get_canvas_feature_command_by_alias("overlay.update_capture_drag")
    if command is not None:
        command(handler, position)

def update_internal_split(handler, position: QPointF) -> None:
    """Update the internal split of the active overlay from cursor position."""
    viewport = handler.store.viewport
    state_q = get_canvas_feature_command_by_alias("overlay.active_state")
    model = state_q(handler.store) if state_q is not None else None
    if model is None:
        return
    geometry = overlay_geometry_at(handler, position)
    if geometry is None:
        size = viewport.geometry_state.active_overlay_screen_size
        if size <= 0:
            return
        center = viewport.geometry_state.active_overlay_screen_center
        radius = size / 2.0
    else:
        center, radius = geometry
        size = radius * 2.0

    if size <= 0 or radius <= 0:
        return

    compare_pos = _scene_compare_pos(handler, position)
    is_horizontal = bool(model["is_horizontal"])
    val = (
        (compare_pos.x - (center.x - radius)) / size
        if not is_horizontal
        else (compare_pos.y - (center.y - radius)) / size
    )
    clamped_val = max(0.0, min(1.0, val))
    if float(model["internal_split"]) != clamped_val:
        command = get_canvas_feature_command_by_alias("overlay.update_internal_split_drag")
        if command is not None:
            command(handler, clamped_val)
