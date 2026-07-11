from __future__ import annotations

from ui.canvas_infra.scene.feature_contract import CanvasSceneFeature

from tabs.image_compare.canvas.features.magnifier.geometry.hit_test import find_magnifier_at_position, get_active_magnifier
from tabs.image_compare.canvas.features.magnifier.scene.apply import apply_magnifier_objects, sync_active_magnifier_geometry
from tabs.image_compare.canvas.features.magnifier.scene.build import (
    MAGNIFIER_Z_ORDER,
    build_magnifier_object,
    build_magnifier_objects,
)
from tabs.image_compare.canvas.features.magnifier.state.store import active_magnifier_id

__all__ = [
    "build_scene_feature",
    "FEATURE",
    "MAGNIFIER_Z_ORDER",
    "build_magnifier_object",
    "build_magnifier_objects",
    "apply_magnifier_objects",
    "sync_active_magnifier_geometry",
    "find_magnifier_at_position",
    "get_active_magnifier",
]


def build_scene_feature() -> CanvasSceneFeature:
    return CanvasSceneFeature(
        name="magnifier",
        build_primary=build_magnifier_objects,
        build_overlay=lambda scene, context: (),
        apply=apply_magnifier_objects,
        hit_test=find_magnifier_at_position,
        resolve_active_object_id=active_magnifier_id,
        sync_geometry=sync_active_magnifier_geometry,
        z_order=MAGNIFIER_Z_ORDER,
        primary_order=10,
        apply_order=10,
        hit_order=10,
    )


FEATURE = build_scene_feature()
