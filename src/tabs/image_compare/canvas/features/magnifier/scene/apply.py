from __future__ import annotations

from PySide6.QtCore import QPointF

from domain.qt_adapters import color_to_qcolor
from domain.types import Color, Point
from tabs.image_compare.canvas.features.magnifier.state.feature_state import get_magnifier_widget_state
from tabs.image_compare.canvas.registry import registry
from ui.canvas_infra.scene.context import CanvasSceneApplyContext
from ui.canvas_infra.scene.pass_contract import SceneVisibility

from tabs.image_compare.canvas.features.magnifier.render.arcs import compute_occluded_capture_arcs
from tabs.image_compare.canvas.features.magnifier.geometry.hit_test import get_active_magnifier


def apply_magnifier_objects(scene, context: CanvasSceneApplyContext) -> None:
    canvas = context.canvas
    geometry_state = context.geometry_state
    scene_visibility = getattr(context, "scene_visibility", SceneVisibility.INTERACTIVE)
    is_interactive_scene = bool(scene_visibility & SceneVisibility.INTERACTIVE)
    store = None
    if getattr(canvas, "runtime_state", None) is not None:
        store = getattr(canvas.runtime_state, "_store", None)

    active_magnifier = get_active_magnifier(scene)
    all_magnifiers = list(scene.iter_objects(kind="magnifier"))
    visible_magnifiers = [
        obj for obj in all_magnifiers if getattr(obj, "visible", False)
    ]
    has_hidden_magnifiers = len(visible_magnifiers) < len(all_magnifiers)
    dragging_capture = bool(
        getattr(getattr(store, "viewport", None), "interaction_state", None)
        and getattr(
            store.viewport.interaction_state, "is_dragging_overlay_handle", False
        )
    )
    capture_circles = []
    hidden_capture_circles = []
    occluded_capture_arcs = []
    hidden_magnifier_circles = []
    magnifier_state = (
        get_magnifier_widget_state(store.viewport.view_state)
        if store is not None
        else None
    )
    _get_capture_state_fn = registry().get_feature_command_by_alias("capture.widget_state")
    capture_state = (
        _get_capture_state_fn(store.viewport.view_state)
        if store is not None and _get_capture_state_fn is not None
        else None
    )
    fallback_capture_color = (
        capture_state.color if capture_state is not None else Color()
    )

    for obj in visible_magnifiers:
        center = getattr(obj, "capture_center", None)
        radius = float(getattr(obj, "capture_radius", 0.0) or 0.0)
        if center is None or radius <= 0:
            continue
        capture_color_q = color_to_qcolor(
            getattr(obj, "capture_color", None) or fallback_capture_color
        )
        capture_circles.append(
            (
                QPointF(center.x, center.y),
                radius,
                capture_color_q,
            )
        )

    if is_interactive_scene and has_hidden_magnifiers:
        for obj in all_magnifiers:
            if getattr(obj, "visible", False):
                continue
            center = getattr(obj, "capture_center", None)
            radius = float(getattr(obj, "capture_radius", 0.0) or 0.0)
            if center is not None and radius > 0:
                hidden_capture_circles.append(
                    (
                        QPointF(center.x, center.y),
                        radius,
                        obj.id == scene.active_object_id,
                    )
                )
            for circle in getattr(obj, "circles", ()) or ():
                if circle.center is None or circle.radius <= 0:
                    continue
                hidden_magnifier_circles.append(
                    (
                        QPointF(circle.center.x, circle.center.y),
                        circle.radius,
                        obj.id == scene.active_object_id,
                    )
                )

    if (
        is_interactive_scene
        and dragging_capture
        and bool(
            magnifier_state is None or magnifier_state.intersection_highlight_enabled
        )
    ):
        occluded_capture_arcs = compute_occluded_capture_arcs(
            all_magnifiers,
            visible_magnifiers,
            scene.active_object_id,
        )

    if active_magnifier is not None and active_magnifier.visible:
        active_capture = getattr(active_magnifier, "capture_center", None)
        active_radius = float(getattr(active_magnifier, "capture_radius", 0.0) or 0.0)
        if active_capture is not None and active_radius > 0:
            active_center = QPointF(active_capture.x, active_capture.y)
            capture_circles = [
                item
                for item in capture_circles
                if not (
                    item[0] == active_center
                    and abs(float(item[1]) - active_radius) <= 1e-6
                )
            ]
            capture_circles.append(
                (
                    active_center,
                    active_radius,
                    color_to_qcolor(
                        getattr(active_magnifier, "capture_color", None)
                        or fallback_capture_color
                    ),
                )
            )

    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None:
        render_scene = getattr(runtime_state, "_render_scene", None)
        if render_scene is not None:
            feature_overrides = getattr(render_scene, "feature_overrides", None)
            if feature_overrides is None:
                feature_overrides = {}
                render_scene.feature_overrides = feature_overrides
            feature_overrides["capture_circles"] = capture_circles
            feature_overrides["hidden_capture_circles"] = hidden_capture_circles
            feature_overrides["occluded_capture_arcs"] = occluded_capture_arcs
            feature_overrides["hidden_magnifier_circles"] = hidden_magnifier_circles

    if active_magnifier is None:
        canvas.set_overlay_coords(None, 0, [], 0)
        sync_active_magnifier_geometry(scene, geometry_state)
        return

    mag_centers = [
        QPointF(circle.center.x, circle.center.y)
        for circle in active_magnifier.circles
        if circle.visible
    ]
    mag_radius = active_magnifier.circles[0].radius if active_magnifier.circles else 0.0
    capture_center = None
    capture_radius = 0.0
    if (
        active_magnifier.capture_center is not None
        and active_magnifier.capture_radius > 0
    ):
        capture_center = QPointF(
            active_magnifier.capture_center.x,
            active_magnifier.capture_center.y,
        )
        capture_radius = active_magnifier.capture_radius

    canvas.set_overlay_coords(capture_center, capture_radius, mag_centers, mag_radius)

    sync_active_magnifier_geometry(scene, geometry_state)


def sync_active_magnifier_geometry(scene, geometry_state) -> None:
    active_magnifier = get_active_magnifier(scene)
    if active_magnifier is None:
        geometry_state.active_overlay_screen_center = Point()
        geometry_state.active_overlay_screen_size = 0
        return
    interactive_circle = active_magnifier.interactive_circle()
    if interactive_circle is not None:
        geometry_state.active_overlay_screen_center = interactive_circle.center
        geometry_state.active_overlay_screen_size = int(
            round(interactive_circle.radius * 2.0)
        )
        return
    geometry_state.active_overlay_screen_center = Point()
    geometry_state.active_overlay_screen_size = 0
