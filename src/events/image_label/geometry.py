from __future__ import annotations

from PySide6.QtCore import QPointF

from domain.types import Point, Rect
from tabs.registry import get_shared_tab_registry

class ImageLabelGeometry:
    """Neutral coordinate-conversion helper for the active tab's canvas.

    This class contains only coordinate math (screen-to-image,
    widget-local-px, content-rect resolution). It never touches a tab's
    canvas widget directly — it asks the active `TabContract` narrow,
    behavioral questions (canvas size, view-transform, content rect) and
    does the math itself, so it never depends on the tab's widget shape.
    """

    def __init__(self, handler):
        self.handler = handler

    def event_position_in_label(self, event, clamp: bool = False) -> QPointF:
        tab = self._active_tab()
        if tab is None:
            return event.position()

        if hasattr(event, "globalPosition"):
            global_pos = event.globalPosition().toPoint()
            mapped_pos = tab.map_global_to_canvas_local(global_pos)
            if mapped_pos is None:
                return event.position()
            local_pos = QPointF(float(mapped_pos.x()), float(mapped_pos.y()))
        else:
            local_pos = event.position()

        if not clamp:
            return local_pos

        size = tab.get_canvas_size()
        if size is None:
            return local_pos
        max_x = max(0.0, float((size[0] or 1) - 1))
        max_y = max(0.0, float((size[1] or 1) - 1))
        return QPointF(
            max(0.0, min(float(local_pos.x()), max_x)),
            max(0.0, min(float(local_pos.y()), max_y)),
        )

    def screen_to_image_rel(self, cursor_pos, clamp: bool = True, *, ignore_pan: bool = False):
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

    def get_zoom_level(self) -> float:
        tab = self._active_tab()
        if tab is None:
            return 1.0
        zoom, _pan_x, _pan_y = tab.get_canvas_zoom_pan()
        return float(zoom or 1.0)

    def _active_tab(self):
        return get_shared_tab_registry().get_active_tab()

    def _clamp_pos_to_image_display_rect(self, cursor_pos: QPointF) -> QPointF:
        rect = self._get_effective_interaction_rect()
        if rect is None or rect.w <= 0 or rect.h <= 0:
            return cursor_pos
        return QPointF(
            max(float(rect.x), min(float(cursor_pos.x()), float(rect.x + rect.w))),
            max(float(rect.y), min(float(cursor_pos.y()), float(rect.y + rect.h))),
        )

    def _get_effective_interaction_rect(self):
        tab = self._active_tab()
        content_rect = tab.get_canvas_content_rect_px() if tab is not None else None
        if content_rect:
            x, y, w, h = content_rect
            return Rect(x, y, w, h)

        rect = self.handler.store.viewport.geometry_state.image_display_rect_on_label
        if rect.w <= 0 or rect.h <= 0:
            return None
        return Rect(int(rect.x), int(rect.y), int(rect.w), int(rect.h))

    def _screen_to_widget_local_px(self, cursor_pos: QPointF, *, ignore_pan: bool = False) -> Point:
        tab = self._active_tab()
        size = tab.get_canvas_size() if tab is not None else None
        if tab is None or size is None:
            return Point(float(cursor_pos.x()), float(cursor_pos.y()))
        width = max(1.0, float(size[0] or 1))
        height = max(1.0, float(size[1] or 1))
        zoom, pan_x, pan_y = tab.get_canvas_zoom_pan()
        if ignore_pan:
            pan_x = 0.0
            pan_y = 0.0
        screen_norm_x = float(cursor_pos.x()) / width
        screen_norm_y = float(cursor_pos.y()) / height
        local_norm_x = (screen_norm_x - 0.5) / zoom + 0.5 - pan_x
        local_norm_y = (screen_norm_y - 0.5) / zoom + 0.5 - pan_y
        return Point(local_norm_x * width, local_norm_y * height)
