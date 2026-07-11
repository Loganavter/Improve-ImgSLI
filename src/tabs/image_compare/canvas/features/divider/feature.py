from __future__ import annotations

from dataclasses import dataclass, field

from domain.types import Color, Rect
from ui.canvas_infra.scene.context import (
    CanvasSceneApplyContext,
    CanvasSceneBuildContext,
)
from ui.canvas_infra.scene.feature_contract import (
    CanvasFeatureZOrder,
    CanvasSceneFeature,
)
from ui.canvas_infra.scene.models import CanvasSceneObject
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

from tabs.image_compare.canvas.features.divider.state.feature_state import get_divider_widget_state

DIVIDER_Z_ORDER = CanvasFeatureZOrder(
    stack_role=CanvasStackRole.UNDERLAY_SPLIT,
)


@dataclass(frozen=True)
class DividerSceneObject(CanvasSceneObject):
    position: float = 0.5
    is_horizontal: bool = False
    color: Color = field(default_factory=Color)
    thickness: int = 1


def build_divider_object(
    *,
    context: CanvasSceneBuildContext,
) -> DividerSceneObject | None:
    view = context.store.viewport.view_state
    divider_state = get_divider_widget_state(view)
    bounds: Rect = context.bounds
    if bounds.w <= 0 or bounds.h <= 0 or not divider_state.visible:
        return None
    return DividerSceneObject(
        id="viewport:divider",
        kind="divider",
        visible=True,
        z_index=DIVIDER_Z_ORDER.priority,
        stack_hint=DIVIDER_Z_ORDER.stack_hint(),
        position=float(view.split_position_visual),
        is_horizontal=bool(view.is_horizontal),
        color=divider_state.color,
        thickness=int(divider_state.thickness),
    )


def build_divider_objects(
    scene,
    context: CanvasSceneBuildContext,
) -> tuple[DividerSceneObject, ...]:
    del scene
    obj = build_divider_object(
        context=context,
    )
    return (obj,) if obj is not None else ()


def apply_divider_object(
    scene,
    context: CanvasSceneApplyContext,
) -> None:
    del scene, context


def build_scene_feature() -> CanvasSceneFeature:
    return CanvasSceneFeature(
        name="divider",
        build_primary=lambda context: (),
        build_overlay=build_divider_objects,
        apply=apply_divider_object,
        z_order=DIVIDER_Z_ORDER,
        overlay_order=10,
        apply_order=40,
    )


FEATURE = build_scene_feature()
