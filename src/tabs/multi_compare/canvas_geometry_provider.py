"""`CanvasGeometryProvider` implementation for `MultiCompareTab`.

See `ui.canvas_infra.viewport.contract.CanvasGeometryProvider` for the
protocol this implements and why it exists: it is the single seam
host-generic event routing/coordinate math uses to query this tab's canvas,
so that code never needs a reference to the canvas widget itself.

The multi-compare canvas is a full-bleed grid (no letterboxing at the top
level — that's an internal per-slot concern), and zoom/pan apply to the
whole grid via `MultiCompareState.zoom/pan_x/pan_y`, so the content rect is
simply the widget's own rect.
"""

from __future__ import annotations

from typing import Any, Callable


class MultiCompareCanvasGeometryProvider:
    def __init__(self, get_canvas: Callable[[], Any | None]):
        self._get_canvas = get_canvas

    @staticmethod
    def _is_same_widget_or_descendant(candidate, target) -> bool:
        current = candidate
        while current is not None:
            if current is target:
                return True
            current = current.parent()
        return False

    def owns_widget(self, candidate: Any) -> bool:
        canvas = self._get_canvas()
        if canvas is None or candidate is None:
            return False
        return self._is_same_widget_or_descendant(candidate, canvas)

    def get_size(self) -> tuple[int, int] | None:
        canvas = self._get_canvas()
        if canvas is None:
            return None
        return (canvas.width(), canvas.height())

    def map_global_to_local(self, global_pos: Any) -> Any | None:
        canvas = self._get_canvas()
        if canvas is None:
            return None
        return canvas.mapFromGlobal(global_pos)

    def get_content_rect_px(self) -> tuple[int, int, int, int] | None:
        canvas = self._get_canvas()
        if canvas is None:
            return None
        w, h = canvas.width(), canvas.height()
        if w <= 0 or h <= 0:
            return None
        return (0, 0, w, h)

    def get_zoom_pan(self) -> tuple[float, float, float]:
        canvas = self._get_canvas()
        if canvas is None:
            return (1.0, 0.0, 0.0)
        state = canvas.state
        return (float(state.zoom), float(state.pan_x), float(state.pan_y))
