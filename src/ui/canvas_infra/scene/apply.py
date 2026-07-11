from __future__ import annotations

from .context import CanvasSceneApplyContext
from .pass_contract import SceneVisibility
from .pipeline import get_scene_appliers

def apply_scene_to_canvas(
    scene,
    canvas,
    geometry_state,
    *,
    session_type: str | None,
    use_quick_overlay: bool,
    scene_visibility: SceneVisibility = SceneVisibility.INTERACTIVE,
) -> None:
    context = CanvasSceneApplyContext(
        canvas=canvas,
        geometry_state=geometry_state,
        use_quick_overlay=use_quick_overlay,
        scene_visibility=scene_visibility,
    )
    for applier in get_scene_appliers(session_type):
        applier(scene, context)
