"""`CanvasGeometryProvider` implementation for `ImageCompareTab`.

See `ui.canvas_infra.viewport.contract.CanvasGeometryProvider` for the
protocol this implements and why it exists: it is the single seam
host-generic event routing/coordinate math uses to query this tab's canvas,
so that code never needs a reference to the canvas widget itself.
"""

from __future__ import annotations

from typing import Any, Callable

from ui.canvas_infra.viewport.state import get_pan_offset_x, get_pan_offset_y, get_zoom_level


class ImageCompareCanvasGeometryProvider:
    def __init__(self, get_label: Callable[[], Any | None]):
        self._get_label = get_label

    @staticmethod
    def _is_same_widget_or_descendant(candidate, target) -> bool:
        current = candidate
        while current is not None:
            if current is target:
                return True
            current = current.parent()
        return False

    def owns_widget(self, candidate: Any) -> bool:
        label = self._get_label()
        if label is None or candidate is None:
            return False
        if self._is_same_widget_or_descendant(candidate, label):
            return True
        for attr_name in ("_window_container", "_canvas_window"):
            owned = getattr(label, attr_name, None)
            if owned is not None and (
                candidate is owned or self._is_same_widget_or_descendant(candidate, owned)
            ):
                return True
        return False

    def get_size(self) -> tuple[int, int] | None:
        label = self._get_label()
        if label is None:
            return None
        return (label.width(), label.height())

    def map_global_to_local(self, global_pos: Any) -> Any | None:
        label = self._get_label()
        if label is None:
            return None
        return label.mapFromGlobal(global_pos)

    def get_content_rect_px(self) -> tuple[int, int, int, int] | None:
        label = self._get_label()
        if label is None:
            return None
        content_rect = label.runtime_state._content_rect_px
        if not content_rect:
            return None
        x, y, w, h = content_rect
        if int(w) <= 0 or int(h) <= 0:
            return None
        return (int(x), int(y), int(w), int(h))

    def get_zoom_pan(self) -> tuple[float, float, float]:
        label = self._get_label()
        if label is None:
            return (1.0, 0.0, 0.0)
        return (get_zoom_level(label), get_pan_offset_x(label), get_pan_offset_y(label))
