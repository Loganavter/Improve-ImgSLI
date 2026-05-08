from __future__ import annotations

from PyQt6.QtCore import QPointF

from domain.types import Point, Rect
from ui.canvas_features.magnifier import MagnifierStoreService
from ui.canvas_features.magnifier.feature import get_active_magnifier
from ui.canvas_features.magnifier.store import active_magnifier_id, magnifier_enabled
from ui.canvas_infra.scene.hit_test import find_scene_object_at_position
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command

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
        self._scene_state = MagnifierStoreService(handler.store)

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

    def screen_to_image_rel(self, cursor_pos):
        label = self._get_image_label()
        if label is not None and hasattr(label, "map_cursor_to_image_rel"):
            mapped = label.map_cursor_to_image_rel(cursor_pos)
            if mapped is not None:
                return mapped

        rect = self._get_effective_interaction_rect()
        if rect is None or rect.w <= 0 or rect.h <= 0:
            return None, None

        local_pos = self._screen_to_widget_local_px(cursor_pos)
        clamped_local_x = max(float(rect.x), min(float(local_pos.x), float(rect.x + rect.w)))
        clamped_local_y = max(float(rect.y), min(float(local_pos.y), float(rect.y + rect.h)))
        img_rel_x = (clamped_local_x - float(rect.x)) / float(rect.w)
        img_rel_y = (clamped_local_y - float(rect.y)) / float(rect.h)
        return img_rel_x, img_rel_y

    def update_state_from_mouse_position(
        self, cursor_pos, respect_magnifier_overlay: bool = True
    ):
        viewport = self.handler.store.viewport
        raw_rel_x, raw_rel_y = self.screen_to_image_rel(cursor_pos)
        if raw_rel_x is None:
            return

        if magnifier_enabled(viewport.view_state):
            position = Point(
                max(0.0, min(1.0, raw_rel_x)),
                max(0.0, min(1.0, raw_rel_y)),
            )
            self._scene_state.move_object_source_position(
                active_magnifier_id(viewport.view_state),
                position,
            )
            if self.handler.presenter and hasattr(
                self.handler.presenter, "update_capture_area_display"
            ):
                self.handler.presenter.update_capture_area_display()
        else:
            rel_pos = raw_rel_x if not viewport.view_state.is_horizontal else raw_rel_y
            new_split_pos = max(0.0, min(1.0, rel_pos))
            old_split = _float_attr(viewport.view_state, "split_position", 0.5)
            old_split_visual = _float_attr(
                viewport.view_state, "split_position_visual", 0.5
            )
            rect = self._get_effective_interaction_rect()
            if rect is None or rect.w <= 0 or rect.h <= 0:
                return
            pixel_pos = (
                int(rect.x + (rect.w * new_split_pos))
                if not viewport.view_state.is_horizontal
                else int(rect.y + (rect.h * new_split_pos))
            )
            viewport.view_state.split_position = new_split_pos
            if viewport.interaction_state.is_dragging_split_line:
                viewport.view_state.split_position_visual = new_split_pos
            if (
                viewport.interaction_state.is_dragging_split_line
                and self.handler.presenter
                and hasattr(self.handler.presenter, "ui")
            ):
                if hasattr(self.handler.presenter.ui, "image_label"):
                    style_command = get_canvas_feature_command(
                        "divider",
                        "runtime.overlay_style",
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

        self.handler.store.emit_viewport_change("interaction")

    def update_magnifier_internal_split(self, position: QPointF):
        viewport = self.handler.store.viewport
        model = self._scene_state.get_active_or_first_magnifier()
        if model is None:
            return
        geometry = self.get_magnifier_geometry_at_position(position)
        if geometry is None:
            size = viewport.geometry_state.magnifier_screen_size
            if size <= 0:
                return
            center = viewport.geometry_state.magnifier_screen_center
            radius = size / 2.0
        else:
            center, radius = geometry
            size = radius * 2.0

        if size <= 0 or radius <= 0:
            return

        compare_pos = self.get_magnifier_compare_pos(position)
        val = (
            (compare_pos.x - (center.x - radius)) / size
            if not model.is_horizontal
            else (compare_pos.y - (center.y - radius)) / size
        )
        clamped_val = max(0.0, min(1.0, val))
        if model.internal_split != clamped_val:
            viewport.interaction_state.magnifier_internal_split_visual = clamped_val
            self._scene_state.set_object_internal_split(
                active_magnifier_id(viewport.view_state),
                clamped_val,
            )
            self.handler.store.emit_viewport_change("interaction")
            if self.handler.main_controller:
                self.handler.main_controller.update_requested.emit()

    def is_point_in_magnifier(self, pos: QPointF, use_internal_coords: bool = True) -> bool:
        return (
            self.get_magnifier_geometry_at_position(
                pos, use_internal_coords=use_internal_coords
            )
            is not None
        )

    def get_magnifier_at_position(
        self, position: QPointF, use_internal_coords: bool = True
    ) -> str | None:
        compare_pos = self.get_magnifier_compare_pos(
            position, use_internal_coords=use_internal_coords
        )
        scene = self._get_canvas_scene()
        if scene is None:
            return None
        match = find_scene_object_at_position(scene, compare_pos)
        if match is not None:
            self._scene_state.set_active_object(match.id)
        return match.id if match is not None else None

    def get_magnifier_geometry_at_position(
        self, pos: QPointF, use_internal_coords: bool = True
    ) -> tuple[Point, float] | None:
        compare_pos = self.get_magnifier_compare_pos(
            pos, use_internal_coords=use_internal_coords
        )
        scene = self._get_canvas_scene()
        if scene is None:
            return None
        magnifier = find_scene_object_at_position(scene, compare_pos)
        if magnifier is None:
            return None
        circle = magnifier.interactive_circle()
        if circle is None:
            return None
        return circle.center, circle.radius

    def get_magnifier_compare_pos(
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

    def _get_magnifier_centers_and_radius(self):
        scene = self._get_canvas_scene()
        if scene is None:
            return [], 0.0, False
        active = get_active_magnifier(scene)
        if active is None:
            return [], 0.0, False
        circles = getattr(active, "circles", ()) or ()
        if not circles:
            return [], 0.0, False
        return [circle.center for circle in circles], circles[0].radius, False

    def _magnifier_to_image_rel(self, cursor_pos):
        viewport = self.handler.store.viewport
        geometry = self.get_magnifier_geometry_at_position(
            cursor_pos,
            use_internal_coords=False,
        )
        if geometry is None:
            return None, None
        center, radius = geometry
        if radius <= 0:
            return None, None

        from shared.image_processing.pipeline import _clamp_capture_position

        model = self._scene_state.get_active_or_first_magnifier()
        if model is None:
            return None, None

        label = self._get_image_label()
        disp_w = max(
            1,
            int(viewport.geometry_state.pixmap_width or (label.width() if label is not None else 0) or 1),
        )
        disp_h = max(
            1,
            int(viewport.geometry_state.pixmap_height or (label.height() if label is not None else 0) or 1),
        )
        cap_x, cap_y = _clamp_capture_position(
            model.position.x,
            model.position.y,
            disp_w,
            disp_h,
            model.capture_size_relative,
        )
        cap_half_disp = model.capture_size_relative * min(disp_w, disp_h) / 2.0
        compare_pos = self.get_magnifier_compare_pos(
            cursor_pos,
            use_internal_coords=False,
        )
        img_rel_x = cap_x + (((compare_pos.x - center.x) / radius) * (cap_half_disp / disp_w))
        img_rel_y = cap_y + (((compare_pos.y - center.y) / radius) * (cap_half_disp / disp_h))
        return img_rel_x, img_rel_y
