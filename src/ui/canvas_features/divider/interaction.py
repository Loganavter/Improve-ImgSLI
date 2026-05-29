"""Divider-side interaction helpers.

Splitter drag math lives here because it's specific to split-line geometry
and the split-line preview overlay; shared coordinate helpers stay neutral
in ``events/image_label/geometry.py``.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias


def apply_split_drag(handler, cursor_pos: QPointF) -> None:
    """Update split position from a cursor drag (split-mode branch)."""
    viewport = handler.store.viewport
    label = handler.geometry._get_image_label()
    zoom_level = float(getattr(label, "zoom_level", 1.0) or 1.0) if label else 1.0
    ignore_pan_for_split = zoom_level <= 1.0
    raw_rel_x, raw_rel_y = handler.geometry.screen_to_image_rel(
        cursor_pos, clamp=True, ignore_pan=ignore_pan_for_split,
    )
    if raw_rel_x is None:
        return

    rel_pos = raw_rel_x if not viewport.view_state.is_horizontal else raw_rel_y
    new_split_pos = max(0.0, min(1.0, rel_pos))
    rect = handler.geometry._get_effective_interaction_rect()
    if rect is None or rect.w <= 0 or rect.h <= 0:
        return
    pixel_pos = (
        int(rect.x + (rect.w * new_split_pos))
        if not viewport.view_state.is_horizontal
        else int(rect.y + (rect.h * new_split_pos))
    )

    command = get_canvas_feature_command_by_alias("splitter.update_drag")
    if command is not None:
        command(handler, new_split_pos)

    if (
        viewport.interaction_state.is_dragging_split_line
        and handler.presenter
        and hasattr(handler.presenter, "ui")
        and hasattr(handler.presenter.ui, "image_label")
    ):
        style_command = get_canvas_feature_command_by_alias("splitter.overlay_style")
        style = (
            style_command(handler.store)
            if style_command is not None
            else {"visible": False, "color": None, "thickness": 0}
        )
        handler.presenter.ui.image_label.set_split_line_params(
            visible=bool(style.get("visible", False)),
            pos=pixel_pos,
            is_horizontal=viewport.view_state.is_horizontal,
            color=style.get("color"),
            thickness=int(style.get("thickness", 0)),
        )
