from __future__ import annotations

from shared.rendering import VirtualCanvasLayout, resolve_virtual_canvas_layout
from ui.canvas_infra.scene.registry import get_canvas_registry

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
    session = store.get_active_workspace_session()
    session_type = session.session_type if session is not None else None
    requirements = []
    for build_requirement in get_canvas_registry(session_type).get_feature_commands_by_id(
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
