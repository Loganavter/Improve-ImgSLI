from __future__ import annotations

from .context import CanvasSceneApplyContext
from .pipeline import SCENE_APPLIERS

def apply_scene_to_canvas(scene, canvas, geometry_state, *, use_quick_overlay: bool) -> None:
    context = CanvasSceneApplyContext(
        canvas=canvas,
        geometry_state=geometry_state,
        use_quick_overlay=use_quick_overlay,
    )
    for applier in SCENE_APPLIERS:
        applier(scene, context)
