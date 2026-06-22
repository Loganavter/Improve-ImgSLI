"""Legacy paint_gl entry point removed during the QRhi migration.

This module is kept as an import target for code that still references
`paint_gl` symbolically (e.g. for instrumentation strings). The QRhi
canvas renders through `rhi_renderer.RhiCanvasRenderer.render(...)` and
no longer needs a paintGL fallback.
"""
from __future__ import annotations


def paint_gl(widget):  # pragma: no cover - retained as a no-op shim
    """No-op shim retained so legacy callers do not crash if any remain."""
    return None
