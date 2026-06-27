from __future__ import annotations

from ui.widgets.canvas.contracts import (
    BaseCanvasProtocol,
    ExportCanvasProtocol,
    GlLikeCanvasProtocol,
)


def get_canvas(ui) -> BaseCanvasProtocol | None:
    return getattr(ui, "image_label", None)


def get_canvas_widget(ui) -> GlLikeCanvasProtocol | None:
    canvas = get_canvas(ui)
    return canvas if isinstance(canvas, GlLikeCanvasProtocol) else None


def get_export_canvas(canvas) -> ExportCanvasProtocol | None:
    return canvas if isinstance(canvas, ExportCanvasProtocol) else None


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
