from __future__ import annotations

from .feature_registry import get_canvas_scene_features

def _sorted_features(order_attr: str):
    return tuple(
        sorted(
            get_canvas_scene_features(),
            key=lambda feature: (getattr(feature, order_attr), feature.name),
        )
    )

SCENE_PRIMARY_BUILDERS = tuple(
    feature.build_primary
    for feature in _sorted_features("primary_order")
)

SCENE_OVERLAY_BUILDERS = tuple(
    feature.build_overlay
    for feature in _sorted_features("overlay_order")
)

SCENE_APPLIERS = tuple(
    feature.apply
    for feature in _sorted_features("apply_order")
)

SCENE_HIT_TESTERS = tuple(
    feature.hit_test
    for feature in _sorted_features("hit_order")
    if feature.hit_test is not None
)
