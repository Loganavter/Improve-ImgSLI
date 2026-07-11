from __future__ import annotations

from domain.qt_adapters import color_to_qcolor
from domain.types import Color
from ui.canvas_infra.scene.context import (
    CanvasSceneApplyContext,
    CanvasSceneBuildContext,
)
from ui.canvas_infra.scene.feature_contract import (
    CanvasFeatureZOrder,
    CanvasSceneFeature,
)
from ui.canvas_infra.scene.models import CanvasSceneGraph, CanvasSceneObject
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

from tabs.image_compare.canvas.features.capture.scene.objects import CaptureSceneObject
from tabs.image_compare.canvas.features.capture.state.feature_state import get_capture_widget_state

CAPTURE_Z_ORDER = CanvasFeatureZOrder(
    stack_role=CanvasStackRole.ANNOTATION_RING,
    always_on_top=True,
)


def _is_visible_magnifier_object(obj: CanvasSceneObject | None) -> bool:
    return bool(
        obj is not None
        and getattr(obj, "kind", None) == "magnifier"
        and getattr(obj, "visible", False)
    )


def get_active_visible_magnifier(scene: CanvasSceneGraph) -> CanvasSceneObject | None:
    active = scene.get_object(scene.active_object_id)
    if _is_visible_magnifier_object(active):
        return active
    for obj in scene.iter_objects(kind="magnifier"):
        if _is_visible_magnifier_object(obj):
            return obj
    return None


def build_capture_object(
    *,
    context: CanvasSceneBuildContext,
    active: CanvasSceneObject | None,
    z_index: int,
) -> CaptureSceneObject | None:
    capture_state = get_capture_widget_state(context.store.viewport.view_state)
    capture_center = (
        getattr(active, "capture_center", None) if active is not None else None
    )
    capture_radius = float(getattr(active, "capture_radius", 0.0) or 0.0)
    if (
        active is None
        or not capture_state.visible
        or capture_center is None
        or capture_radius <= 0
    ):
        return None
    return CaptureSceneObject(
        id=f"{active.id}:capture",
        kind="capture",
        visible=True,
        z_index=z_index,
        stack_hint=CAPTURE_Z_ORDER.stack_hint(priority=z_index),
        center=capture_center,
        radius=capture_radius,
        color=capture_state.color,
    )


def build_capture_objects(
    scene,
    context: CanvasSceneBuildContext,
) -> tuple[CaptureSceneObject, ...]:
    active = get_active_visible_magnifier(scene)
    obj = build_capture_object(
        context=context,
        active=active,
        z_index=CAPTURE_Z_ORDER.priority,
    )
    return (obj,) if obj is not None else ()


def apply_capture_object(scene, context: CanvasSceneApplyContext) -> None:
    canvas = context.canvas
    capture_object = scene.find_first("capture")
    if isinstance(capture_object, CaptureSceneObject):
        canvas.set_capture_color(color_to_qcolor(capture_object.color))
        return
    canvas.set_capture_color(color_to_qcolor(Color()))


def build_scene_feature() -> CanvasSceneFeature:
    return CanvasSceneFeature(
        name="capture",
        build_primary=lambda context: (),
        build_overlay=build_capture_objects,
        apply=apply_capture_object,
        z_order=CAPTURE_Z_ORDER,
        overlay_order=20,
        apply_order=30,
    )


FEATURE = build_scene_feature()
