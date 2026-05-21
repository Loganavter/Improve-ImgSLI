from __future__ import annotations

from .context import CanvasSceneApplyContext
from .gl_pass_contract import SceneVisibility
from .pipeline import SCENE_APPLIERS

def apply_scene_to_canvas(
    scene,
    canvas,
    geometry_state,
    *,
    use_quick_overlay: bool,
    scene_visibility: SceneVisibility = SceneVisibility.INTERACTIVE,
) -> None:
    context = CanvasSceneApplyContext(
        canvas=canvas,
        geometry_state=geometry_state,
        use_quick_overlay=use_quick_overlay,
        scene_visibility=scene_visibility,
    )
    for applier in SCENE_APPLIERS:
        applier(scene, context)
