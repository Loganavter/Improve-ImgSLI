from __future__ import annotations

from PyQt6.QtCore import QPointF

from domain.types import Point, Rect
from ui.canvas_infra.scene.hit_test import find_scene_object_at_position
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command, get_canvas_feature_command_by_alias

def _float_attr(obj, attr: str, default: float) -> float:
    if obj is None:
        return float(default)
    value = getattr(obj, attr, None)
    if value is None:
        return float(default)
    return float(value)

class ImageLabelGeometry:
    def __init__(self, handler):
        self.handler = handler

    def event_position_in_label(self, event, clamp: bool = False) -> QPointF:
        label = self._get_image_label()
        if label is None:
            return event.position()

        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
            mapped_pos = label.mapFromGlobal(global_pos)
            local_pos = QPointF(float(mapped_pos.x()), float(mapped_pos.y()))
        else:
            local_pos = event.position()

        if not clamp:
            return local_pos

        max_x = max(0.0, float((label.width() or 1) - 1))
        max_y = max(0.0, float((label.height() or 1) - 1))
        return QPointF(
            max(0.0, min(float(local_pos.x()), max_x)),
            max(0.0, min(float(local_pos.y()), max_y)),
        )

    def screen_to_image_rel(self, cursor_pos, clamp: bool = True):
        label = self._get_image_label()
        if label is not None and hasattr(label, "map_cursor_to_image_rel"):
            mapped = label.map_cursor_to_image_rel(cursor_pos)
            if mapped is not None:
                return mapped

        rect = self._get_effective_interaction_rect()
        if rect is None or rect.w <= 0 or rect.h <= 0:
            return None, None

        local_pos = self._screen_to_widget_local_px(cursor_pos)
        local_x = float(local_pos.x)
        local_y = float(local_pos.y)
        if clamp:
            local_x = max(float(rect.x), min(local_x, float(rect.x + rect.w)))
            local_y = max(float(rect.y), min(local_y, float(rect.y + rect.h)))
        img_rel_x = (local_x - float(rect.x)) / float(rect.w)
        img_rel_y = (local_y - float(rect.y)) / float(rect.h)
        return img_rel_x, img_rel_y

    def update_state_from_mouse_position(
        self, cursor_pos, respect_overlay: bool = True
    ):
        viewport = self.handler.store.viewport
        raw_rel_x, raw_rel_y = self.screen_to_image_rel(
            cursor_pos,
            clamp=not self.handler.store.viewport.view_state.overlay_enabled,
        )
        if raw_rel_x is None:
            return

        if self.handler.store.viewport.view_state.overlay_enabled:
            position = Point(
                float(raw_rel_x),
                float(raw_rel_y),
            )
            command = get_canvas_feature_command_by_alias(
                "overlay.update_capture_drag",
            )
            if command is not None:
                command(self.handler, position)
        else:
            rel_pos = raw_rel_x if not viewport.view_state.is_horizontal else raw_rel_y
            new_split_pos = max(0.0, min(1.0, rel_pos))
            rect = self._get_effective_interaction_rect()
            if rect is None or rect.w <= 0 or rect.h <= 0:
                return
            pixel_pos = (
                int(rect.x + (rect.w * new_split_pos))
                if not viewport.view_state.is_horizontal
                else int(rect.y + (rect.h * new_split_pos))
            )
            command = get_canvas_feature_command_by_alias(
                "splitter.update_drag",
            )
            if command is not None:
                command(self.handler, new_split_pos)
            if (
                viewport.interaction_state.is_dragging_split_line
                and self.handler.presenter
                and hasattr(self.handler.presenter, "ui")
            ):
                if hasattr(self.handler.presenter.ui, "image_label"):
                    style_command = get_canvas_feature_command_by_alias(
                        "splitter.overlay_style",
                    )
                    style = (
                        style_command(self.handler.store)
                        if style_command is not None
                        else {"visible": False, "color": None, "thickness": 0}
                    )
                    self.handler.presenter.ui.image_label.set_split_line_params(
                        visible=bool(style.get("visible", False)),
                        pos=pixel_pos,
                        is_horizontal=viewport.view_state.is_horizontal,
                        color=style.get("color"),
                        thickness=int(style.get("thickness", 0)),
                    )

    def update_overlay_internal_split(self, position: QPointF):
        viewport = self.handler.store.viewport
        _q = get_canvas_feature_command_by_alias("overlay.active_state")
        model = _q(self.handler.store) if _q is not None else None
        if model is None:
            return
        geometry = self.get_overlay_geometry_at_position(position)
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

        compare_pos = self.get_scene_compare_pos(position)
        val = (
            (compare_pos.x - (center.x - radius)) / size
            if not bool(model["is_horizontal"])
            else (compare_pos.y - (center.y - radius)) / size
        )
        clamped_val = max(0.0, min(1.0, val))
        if float(model["internal_split"]) != clamped_val:
            command = get_canvas_feature_command_by_alias(
                "overlay.update_internal_split_drag",
            )
            if command is not None:
                command(self.handler, clamped_val)

    def is_point_in_overlay(self, pos: QPointF, use_internal_coords: bool = True) -> bool:
        return (
            self.get_overlay_geometry_at_position(
                pos, use_internal_coords=use_internal_coords
            )
            is not None
        )

    def get_overlay_at_position(
        self, position: QPointF, use_internal_coords: bool = True
    ) -> str | None:
        compare_pos = self.get_scene_compare_pos(
            position, use_internal_coords=use_internal_coords
        )
        scene = self._get_canvas_scene()
        if scene is None:
            return None
        match = find_scene_object_at_position(scene, compare_pos)
        if match is not None:
            _set_active = get_canvas_feature_command_by_alias(
                "overlay.set_active_instance",
            )
            if _set_active is not None:
                _set_active(self.handler.store, match.id)
        return match.id if match is not None else None

    def get_overlay_geometry_at_position(
        self, pos: QPointF, use_internal_coords: bool = True
    ) -> tuple[Point, float] | None:
        compare_pos = self.get_scene_compare_pos(
            pos, use_internal_coords=use_internal_coords
        )
        scene = self._get_canvas_scene()
        if scene is None:
            return None
        scene_object = find_scene_object_at_position(scene, compare_pos)
        if scene_object is None:
            return None
        circle = scene_object.interactive_circle()
        if circle is None:
            return None
        return circle.center, circle.radius

    def get_scene_compare_pos(
        self, pos: QPointF, use_internal_coords: bool = True
    ) -> Point:
        if use_internal_coords:
            return self._screen_to_widget_local_px(pos)
        return Point(float(pos.x()), float(pos.y()))

    def _get_image_label(self):
        if self.handler.presenter and hasattr(self.handler.presenter, "ui"):
            return getattr(self.handler.presenter.ui, "image_label", None)
        return None

    def _get_canvas_scene(self):
        label = self._get_image_label()
        state = getattr(label, "runtime_state", None) if label is not None else None
        return getattr(state, "_canvas_scene_graph", None) if state is not None else None

    def _clamp_pos_to_image_display_rect(self, cursor_pos: QPointF) -> QPointF:
        rect = self._get_effective_interaction_rect()
        if rect is None or rect.w <= 0 or rect.h <= 0:
            return cursor_pos
        return QPointF(
            max(float(rect.x), min(float(cursor_pos.x()), float(rect.x + rect.w))),
            max(float(rect.y), min(float(cursor_pos.y()), float(rect.y + rect.h))),
        )

    def _get_effective_interaction_rect(self):
        label = self._get_image_label()
        state = getattr(label, "runtime_state", None) if label is not None else None
        content_rect = getattr(state, "_content_rect_px", None) if state is not None else None
        if content_rect:
            x, y, w, h = content_rect
            if int(w) > 0 and int(h) > 0:
                return Rect(int(x), int(y), int(w), int(h))

        rect = self.handler.store.viewport.geometry_state.image_display_rect_on_label
        if rect.w <= 0 or rect.h <= 0:
            return None
        return Rect(int(rect.x), int(rect.y), int(rect.w), int(rect.h))

    def _screen_to_widget_local_px(self, cursor_pos: QPointF) -> Point:
        label = self._get_image_label()
        if label is None:
            return Point(float(cursor_pos.x()), float(cursor_pos.y()))
        width = max(1.0, float(label.width() or 1))
        height = max(1.0, float(label.height() or 1))
        zoom = float(getattr(label, "zoom_level", 1.0) or 1.0)
        pan_x = float(getattr(label, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(label, "pan_offset_y", 0.0) or 0.0)
        screen_norm_x = float(cursor_pos.x()) / width
        screen_norm_y = float(cursor_pos.y()) / height
        local_norm_x = (screen_norm_x - 0.5) / zoom + 0.5 - pan_x
        local_norm_y = (screen_norm_y - 0.5) / zoom + 0.5 - pan_y
        return Point(local_norm_x * width, local_norm_y * height)
