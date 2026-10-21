"""Shared render-mode definitions for the canvas stack."""

from __future__ import annotations

#: objectName the exporter stamps on its offscreen canvas widget — the single
#: signal both the render context and the frame setup use to resolve export mode.
EXPORT_CANVAS_OBJECT_NAME = "gpu_export_canvas"
