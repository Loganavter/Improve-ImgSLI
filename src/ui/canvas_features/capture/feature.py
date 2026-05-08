from __future__ import annotations

from domain.qt_adapters import color_to_qcolor
from domain.types import Color

from ui.canvas_infra.scene.context import CanvasSceneApplyContext, CanvasSceneBuildContext
from ui.canvas_infra.scene.feature_contract import CanvasFeatureZOrder, CanvasSceneFeature
from ui.canvas_infra.scene.models import CanvasSceneGraph
from ui.canvas_infra.scene.stacking import CanvasStackLayer
from ui.canvas_features.magnifier.scene_objects import MagnifierSceneObject

from .scene_objects import CaptureSceneObject
from .state import get_capture_widget_state

CAPTURE_Z_ORDER = CanvasFeatureZOrder(
    layer=CanvasStackLayer.CAPTURE,
    priority=100,
    always_on_top=True,
)

def get_active_visible_magnifier(scene: CanvasSceneGraph) -> MagnifierSceneObject | None:
    active = scene.get_object(scene.active_object_id)
    if isinstance(active, MagnifierSceneObject) and active.visible:
        return active
    for obj in scene.iter_objects(kind="magnifier"):
        if isinstance(obj, MagnifierSceneObject) and obj.visible:
            return obj
    return None

def build_capture_object(
    *,
    context: CanvasSceneBuildContext,
    active: MagnifierSceneObject | None,
    z_index: int,
) -> CaptureSceneObject | None:
    capture_state = get_capture_widget_state(context.store.viewport.view_state)
    if (
        active is None
        or not capture_state.visible
        or active.capture_center is None
        or active.capture_radius <= 0
    ):
        return None
    return CaptureSceneObject(
        id=f"{active.id}:capture",
        kind="capture",
        visible=True,
        z_index=z_index,
        stack_hint=CAPTURE_Z_ORDER.stack_hint(priority=z_index),
        center=active.capture_center,
        radius=active.capture_radius,
        color=active.capture_ring_color,
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

FEATURE = CanvasSceneFeature(
    name="capture",
    build_primary=lambda context: (),
    build_overlay=build_capture_objects,
    apply=apply_capture_object,
    z_order=CAPTURE_Z_ORDER,
    overlay_order=20,
    apply_order=30,
)
