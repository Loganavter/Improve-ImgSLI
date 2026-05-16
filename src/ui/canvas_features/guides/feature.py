from __future__ import annotations

from domain.qt_adapters import color_to_qcolor
from domain.types import Color

from ui.canvas_infra.scene.context import CanvasSceneApplyContext, CanvasSceneBuildContext
from ui.canvas_infra.scene.feature_contract import CanvasFeatureZOrder, CanvasSceneFeature
from ui.canvas_infra.scene.models import CanvasSceneGraph, CanvasSceneObject
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

from .scene_objects import GuidesSceneObject
from .state import get_guides_widget_state

GUIDES_Z_ORDER = CanvasFeatureZOrder(
    stack_role=CanvasStackRole.ANNOTATION_GUIDE,
    always_on_top=True,
)

def _is_visible_magnifier_object(obj: CanvasSceneObject) -> bool:
    return bool(
        getattr(obj, "kind", None) == "magnifier"
        and getattr(obj, "visible", False)
    )

def get_visible_magnifiers(scene: CanvasSceneGraph) -> tuple[CanvasSceneObject, ...]:
    return tuple(
        obj
        for obj in scene.iter_objects(kind="magnifier")
        if _is_visible_magnifier_object(obj)
    )

def build_guides_object(
    *,
    context: CanvasSceneBuildContext,
    magnifier: CanvasSceneObject | None,
    z_index: int,
) -> GuidesSceneObject | None:
    view_state = context.store.viewport.view_state
    guides_state = get_guides_widget_state(view_state)
    diff_mode = getattr(view_state, "diff_mode", "off")
    circles = tuple(getattr(magnifier, "circles", ()) or ()) if magnifier is not None else ()
    capture_center = getattr(magnifier, "capture_center", None) if magnifier is not None else None
    capture_radius = float(getattr(magnifier, "capture_radius", 0.0) or 0.0)
    show_laser = bool(getattr(magnifier, "show_laser", True)) if magnifier is not None else True
    guides_color = getattr(magnifier, "guides_color", None) if magnifier is not None else None
    if (
        magnifier is None
        or not guides_state.enabled
        or not show_laser
        or capture_center is None
        or capture_radius <= 0
        or not circles
    ):
        return None

    visible_circles = tuple(
        circle for circle in circles if getattr(circle, "visible", False)
    )
    if not visible_circles:
        return None

    target_circles = visible_circles
    if diff_mode not in ("highlight", "grayscale", "ssim", "edges"):
        target_circles = tuple(
            circle for circle in visible_circles if circle.role != "center"
        )
        if not target_circles:
            return None
    target_centers = tuple(circle.center for circle in target_circles)
    target_radii = tuple(float(circle.radius) for circle in target_circles)
    target_radius = target_radii[0] if target_radii else 0.0

    return GuidesSceneObject(
        id=f"{magnifier.id}:guides",
        kind="guides",
        visible=True,
        z_index=z_index,
        stack_hint=GUIDES_Z_ORDER.stack_hint(priority=z_index),
        source_center=capture_center,
        target_centers=target_centers,
        source_radius=capture_radius,
        target_radius=target_radius,
        target_radii=target_radii,
        color=guides_color or guides_state.color,
        thickness=guides_state.thickness,
    )

def build_guides_objects(
    scene,
    context: CanvasSceneBuildContext,
) -> tuple[GuidesSceneObject, ...]:
    visible = get_visible_magnifiers(scene)
    objects = []
    for index, magnifier in enumerate(visible):
        obj = build_guides_object(
            context=context,
            magnifier=magnifier,
            z_index=GUIDES_Z_ORDER.priority + index,
        )
        if obj is not None:
            objects.append(obj)
    return tuple(objects)

def apply_guides_object(scene, context: CanvasSceneApplyContext) -> None:
    canvas = context.canvas
    guides_objects = [
        obj for obj in scene.iter_objects(kind="guides")
        if isinstance(obj, GuidesSceneObject) and obj.visible
    ]
    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None and hasattr(runtime_state, "_guide_sets"):
        runtime_state._guide_sets = [
            (
                guides_object.source_center,
                float(guides_object.source_radius),
                tuple(guides_object.target_centers),
                tuple(guides_object.target_radii) or float(guides_object.target_radius),
                color_to_qcolor(guides_object.color),
            )
            for guides_object in guides_objects
            if guides_object.source_center is not None and guides_object.target_centers
        ]
    if guides_objects:
        guides_object = guides_objects[0]
        canvas.set_guides_params(
            guides_object.visible,
            color_to_qcolor(guides_object.color),
            guides_object.thickness,
        )
        return
    if runtime_state is not None and hasattr(runtime_state, "_guide_sets"):
        runtime_state._guide_sets = []
    canvas.set_guides_params(False, color_to_qcolor(Color()), 1)

def build_scene_feature() -> CanvasSceneFeature:
    return CanvasSceneFeature(
        name="guides",
        build_primary=lambda context: (),
        build_overlay=build_guides_objects,
        apply=apply_guides_object,
        z_order=GUIDES_Z_ORDER,
        overlay_order=30,
        apply_order=20,
    )

FEATURE = build_scene_feature()
