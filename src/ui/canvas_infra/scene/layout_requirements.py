from __future__ import annotations

import logging

from shared.rendering import VirtualCanvasLayout, resolve_virtual_canvas_layout
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_commands_by_id

_dlog = logging.getLogger("ImproveImgSLI.divider_debug")

def resolve_feature_virtual_layout(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> VirtualCanvasLayout | None:
    """Union every registered ``render.layout_requirement`` into one
    ``VirtualCanvasLayout``. Single owner of this computation — live canvas
    and export/snapshot rendering must both call this, never recompute the
    union locally, so a new feature's layout requirement is honored
    everywhere without touching either caller."""
    if store is None or drawing_width <= 0 or drawing_height <= 0:
        return None
    requirements = []
    for build_requirement in get_canvas_feature_commands_by_id(
        "render.layout_requirement"
    ):
        requirement = build_requirement(
            store,
            drawing_width=drawing_width,
            drawing_height=drawing_height,
        )
        if requirement is not None:
            requirements.append(requirement)
    layout = resolve_virtual_canvas_layout(requirements)
    return layout
