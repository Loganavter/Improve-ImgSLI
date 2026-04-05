from __future__ import annotations

from PyQt6.QtCore import QPointF

from domain.qt_adapters import color_to_qcolor
from domain.types import Point, Rect

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

        if viewport.view_state.use_magnifier:
            viewport.view_state.capture_position_relative = Point(
                max(0.0, min(1.0, raw_rel_x)),
                max(0.0, min(1.0, raw_rel_y)),
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
                    self.handler.presenter.ui.image_label.set_split_line_params(
                        visible=True,
                        pos=pixel_pos,
                        is_horizontal=viewport.view_state.is_horizontal,
                        color=color_to_qcolor(viewport.render_config.divider_line_color),
                        thickness=viewport.render_config.divider_line_thickness,
                    )

        self.handler.store.emit_viewport_change("interaction")

    def update_magnifier_internal_split(self, position: QPointF):
        viewport = self.handler.store.viewport
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
            if not viewport.view_state.magnifier_is_horizontal
            else (compare_pos.y - (center.y - radius)) / size
        )
        clamped_val = max(0.0, min(1.0, val))
        if viewport.view_state.magnifier_internal_split != clamped_val:
            viewport.view_state.magnifier_internal_split = clamped_val
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
        if self.is_point_in_magnifier(position, use_internal_coords=use_internal_coords):
            return self.handler.store.viewport.view_state.active_magnifier_id or "default"
        return None

    def get_magnifier_geometry_at_position(
        self, pos: QPointF, use_internal_coords: bool = True
    ) -> tuple[Point, float] | None:
        mag_centers, mag_radius, use_local_coords = self._get_magnifier_centers_and_radius()
        if mag_radius <= 0 or not mag_centers:
            return None
        compare_pos = self.get_magnifier_compare_pos(
            pos, use_internal_coords=use_internal_coords
        )
        if use_internal_coords and use_local_coords:
            label = self._get_image_label()
            zoom = float(getattr(label, "zoom_level", 1.0) or 1.0) if label is not None else 1.0
            zoom = max(zoom, 1e-6)
            mag_centers = [
                self._screen_to_widget_local_px(QPointF(float(center.x), float(center.y)))
                for center in mag_centers
            ]
            mag_radius = float(mag_radius) / zoom
        radius_squared = mag_radius * mag_radius
        best_center = None
        best_distance = None
        for center in mag_centers:
            dx = compare_pos.x - center.x
            dy = compare_pos.y - center.y
            distance_squared = dx * dx + dy * dy
            if distance_squared > radius_squared:
                continue
            if best_distance is None or distance_squared < best_distance:
                best_distance = distance_squared
                best_center = center
        if best_center is None:
            return None
        return best_center, mag_radius

    def get_magnifier_compare_pos(
        self, pos: QPointF, use_internal_coords: bool = True
    ) -> Point:
        mag_centers, _, use_local_coords = self._get_magnifier_centers_and_radius()
        if use_internal_coords and use_local_coords and mag_centers:
            return self._screen_to_widget_local_px(pos)
        return Point(float(pos.x()), float(pos.y()))

    def _get_image_label(self):
        if self.handler.presenter and hasattr(self.handler.presenter, "ui"):
            return getattr(self.handler.presenter.ui, "image_label", None)
        return None

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
        viewport = self.handler.store.viewport
        image_label = self._get_image_label()
        mag_centers = []
        mag_radius = 0.0
        use_local_coords = False

        if image_label is not None:
            raw_centers = getattr(image_label, "_magnifier_centers", None) or []
            raw_radius = float(getattr(image_label, "_magnifier_radius", 0.0) or 0.0)
            if raw_centers and raw_radius > 0:
                mag_centers = [
                    Point(float(center.x()), float(center.y())) for center in raw_centers
                ]
                mag_radius = raw_radius
                use_local_coords = True

        if not mag_centers:
            size = float(viewport.geometry_state.magnifier_screen_size or 0.0)
            if size > 0:
                mag_centers = [viewport.geometry_state.magnifier_screen_center]
                mag_radius = size / 2.0

        return mag_centers, mag_radius, use_local_coords

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
            viewport.view_state.capture_position_relative.x,
            viewport.view_state.capture_position_relative.y,
            disp_w,
            disp_h,
            viewport.view_state.capture_size_relative,
        )
        cap_half_disp = viewport.view_state.capture_size_relative * min(disp_w, disp_h) / 2.0
        compare_pos = self.get_magnifier_compare_pos(
            cursor_pos,
            use_internal_coords=False,
        )
        img_rel_x = cap_x + (((compare_pos.x - center.x) / radius) * (cap_half_disp / disp_w))
        img_rel_y = cap_y + (((compare_pos.y - center.y) / radius) * (cap_half_disp / disp_h))
        return img_rel_x, img_rel_y
