"""This tab's own canvas feature registry accessor.

multi_compare features are only ever visible to multi_compare — no
call site in this tab needs to resolve "which tab" at runtime, since
registration happens once per tab type at startup. See
docs/dev/rendering/package-structure.md (one registry per tab type).
"""
from __future__ import annotations

from ui.canvas_infra.scene.registry import CanvasFeatureRegistry, get_canvas_registry


def registry() -> CanvasFeatureRegistry:
    return get_canvas_registry("multi_compare")
