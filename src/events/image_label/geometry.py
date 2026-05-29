from __future__ import annotations

from PyQt6.QtCore import QPointF

from domain.types import Point, Rect


class ImageLabelGeometry:
    """Neutral coordinate-conversion helper for the image-label widget.

    This class contains only coordinate math (screen-to-image,
    widget-local-px, content-rect resolution). Feature-specific interaction
    logic lives in each feature's ``interaction.py`` module — see
    ``ui/canvas_features/magnifier/interaction.py`` and
    ``ui/canvas_features/divider/interaction.py``.
    """

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

    def screen_to_image_rel(self, cursor_pos, clamp: bool = True, *, ignore_pan: bool = False):
        label = self._get_image_label()
        if label is not None and hasattr(label, "map_cursor_to_image_rel"):
            mapped = label.map_cursor_to_image_rel(cursor_pos)
            if mapped is not None:
                return mapped

        rect = self._get_effective_interaction_rect()
        if rect is None or rect.w <= 0 or rect.h <= 0:
            return None, None

        local_pos = self._screen_to_widget_local_px(cursor_pos, ignore_pan=ignore_pan)
        local_x = float(local_pos.x)
        local_y = float(local_pos.y)
        if clamp:
            local_x = max(float(rect.x), min(local_x, float(rect.x + rect.w)))
            local_y = max(float(rect.y), min(local_y, float(rect.y + rect.h)))
        img_rel_x = (local_x - float(rect.x)) / float(rect.w)
        img_rel_y = (local_y - float(rect.y)) / float(rect.h)
        return img_rel_x, img_rel_y

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

    def _screen_to_widget_local_px(self, cursor_pos: QPointF, *, ignore_pan: bool = False) -> Point:
        label = self._get_image_label()
        if label is None:
            return Point(float(cursor_pos.x()), float(cursor_pos.y()))
        width = max(1.0, float(label.width() or 1))
        height = max(1.0, float(label.height() or 1))
        zoom = float(getattr(label, "zoom_level", 1.0) or 1.0)
        if ignore_pan:
            pan_x = 0.0
            pan_y = 0.0
        else:
            pan_x = float(getattr(label, "pan_offset_x", 0.0) or 0.0)
            pan_y = float(getattr(label, "pan_offset_y", 0.0) or 0.0)
        screen_norm_x = float(cursor_pos.x()) / width
        screen_norm_y = float(cursor_pos.y()) / height
        local_norm_x = (screen_norm_x - 0.5) / zoom + 0.5 - pan_x
        local_norm_y = (screen_norm_y - 0.5) / zoom + 0.5 - pan_y
        return Point(local_norm_x * width, local_norm_y * height)
