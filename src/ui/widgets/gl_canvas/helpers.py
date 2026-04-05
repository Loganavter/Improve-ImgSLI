from __future__ import annotations

from ui.widgets.gl_canvas.contracts import (
    BaseCanvasProtocol,
    ExportCanvasProtocol,
    GlLikeCanvasProtocol,
)

def get_canvas(ui) -> BaseCanvasProtocol | None:
    return getattr(ui, "image_label", None)

def get_gl_like_canvas(ui) -> GlLikeCanvasProtocol | None:
    canvas = get_canvas(ui)
    return canvas if isinstance(canvas, GlLikeCanvasProtocol) else None

def get_export_canvas(canvas) -> ExportCanvasProtocol | None:
    return canvas if isinstance(canvas, ExportCanvasProtocol) else None

def uses_quick_overlay(canvas) -> bool:
    return bool(getattr(canvas, "uses_quick_canvas_overlay", False))

def supports_legacy_magnifier(canvas) -> bool:
    return bool(getattr(canvas, "supports_legacy_gl_magnifier", False))

def reset_canvas_overlays(canvas: BaseCanvasProtocol) -> None:
    canvas.clear_magnifier_gpu()
    canvas.set_magnifier_content(None, None)
    canvas.set_overlay_coords(None, 0, [], 0)
    canvas.set_capture_area(None, 0)

def clear_canvas_diff_source(canvas: BaseCanvasProtocol) -> None:
    canvas.upload_diff_source_pil_image(None)
