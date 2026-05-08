from __future__ import annotations

from domain.types import Point

from .models import CanvasSceneGraph
from .pipeline import SCENE_HIT_TESTERS

def find_scene_object_at_position(
    scene: CanvasSceneGraph,
    point: Point,
):
    for hit_tester in SCENE_HIT_TESTERS:
        match = hit_tester(scene, point)
        if match is not None:
            return match
    return None
