from __future__ import annotations

from tabs.image_compare.canvas.contracts import (
    BaseCanvasProtocol,
    ExportCanvasProtocol,
    GlLikeCanvasProtocol,
)
from tabs.image_compare.canvas.widget import CanvasWidget


def get_canvas(widget) -> BaseCanvasProtocol | None:
    return getattr(widget, "image_label", None)


def get_canvas_widget(widget) -> GlLikeCanvasProtocol | None:
    # Nominal isinstance() against the concrete class instead of the
    # runtime_checkable Protocol: this runs on every drag/render frame, and
    # typing.Protocol's structural check (__instancecheck__) walks every
    # declared attribute via inspect.getattr_static, ~30x the cost of a
    # normal isinstance for this protocol. CanvasWidget is the only
    # implementation (see tests/contracts/test_canvas_protocols.py), so the
    # result is identical.
    canvas = get_canvas(widget)
    return canvas if isinstance(canvas, CanvasWidget) else None


def get_export_canvas(canvas) -> ExportCanvasProtocol | None:
    return canvas if isinstance(canvas, CanvasWidget) else None


def reset_canvas_overlays(canvas: BaseCanvasProtocol) -> None:
    canvas.clear_feature_overlay_gpu()
    canvas.set_feature_overlay_content(None, None)
    canvas.set_overlay_coords(None, 0, [], 0)
    canvas.set_capture_area(None, 0)
    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None and hasattr(runtime_state, "_capture_circles"):
        runtime_state._capture_circles = []
        runtime_state._guide_sets = []
        runtime_state._hidden_capture_circles = []
        runtime_state._occluded_capture_arcs = []
        runtime_state._hidden_overlay_circles = []


def clear_canvas_diff_source(canvas: BaseCanvasProtocol) -> None:
    canvas.upload_diff_source_pil_image(None)
