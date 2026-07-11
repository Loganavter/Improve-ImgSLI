from __future__ import annotations

from .registry import get_canvas_registry

def _sorted_features(session_type: str | None, order_attr: str):
    return tuple(
        sorted(
            get_canvas_registry(session_type).get_scene_features(),
            key=lambda feature: (getattr(feature, order_attr), feature.name),
        )
    )

def get_scene_primary_builders(session_type: str | None):
    return tuple(
        feature.build_primary
        for feature in _sorted_features(session_type, "primary_order")
    )

def get_scene_overlay_builders(session_type: str | None):
    return tuple(
        feature.build_overlay
        for feature in _sorted_features(session_type, "overlay_order")
    )

def get_scene_appliers(session_type: str | None):
    return tuple(
        feature.apply
        for feature in _sorted_features(session_type, "apply_order")
    )

def get_scene_hit_testers(session_type: str | None):
    return tuple(
        feature.hit_test
        for feature in _sorted_features(session_type, "hit_order")
        if feature.hit_test is not None
    )
