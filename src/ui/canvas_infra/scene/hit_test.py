from __future__ import annotations

from domain.types import Point

from .models import CanvasSceneGraph
from .pipeline import get_scene_hit_testers

def find_scene_object_at_position(
    scene: CanvasSceneGraph,
    point: Point,
    *,
    session_type: str | None,
):
    for hit_tester in get_scene_hit_testers(session_type):
        match = hit_tester(scene, point)
        if match is not None:
            return match
    return None
