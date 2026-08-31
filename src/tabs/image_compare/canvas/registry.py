"""This tab's own canvas feature registry accessor.

image_compare features are only ever visible to image_compare — no
call site in this tab needs to resolve "which tab" at runtime, since
registration happens once per tab type at startup. See
docs/dev/CANVAS_FEATURE_REGISTRY_PER_TAB.md.

Phase 2 canvas-only overlay: ``drag_drop_overlay`` is a pure RHI feature
(``canvas/features/drag_drop_overlay`` — ``DragDropOverlayPass`` via
``FullscreenOverlayTexturePass``); its ``WIDGET_FEATURE`` is auto-discovered
and its ``RENDER_PASSES`` are picked up via ``registry().get_render_passes()``
after ``register_canvas_feature_package("image_compare", features_pkg)`` in
``tab.py:register_canvas_features``.
"""
from __future__ import annotations

from ui.canvas_infra.scene.registry import CanvasFeatureRegistry, get_canvas_registry


def registry() -> CanvasFeatureRegistry:
    return get_canvas_registry("image_compare")
