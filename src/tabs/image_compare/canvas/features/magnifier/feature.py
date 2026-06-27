from __future__ import annotations

import math

from PySide6.QtCore import QPointF

from domain.qt_adapters import color_to_qcolor
from domain.types import Color, Point, Rect
from tabs.image_compare.canvas.features.magnifier.constants import (
    MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE as THRESHOLD,
)
from tabs.image_compare.canvas.features.magnifier.state import get_magnifier_widget_state
from tabs.image_compare.canvas.features.magnifier.store import (
    active_magnifier_id,
    iter_magnifier_models,
)
from ui.canvas_infra.scene.context import (
    CanvasSceneApplyContext,
    CanvasSceneBuildContext,
)
from ui.canvas_infra.scene.feature_contract import (
    CanvasFeatureZOrder,
    CanvasSceneFeature,
)
from ui.canvas_infra.scene.pass_contract import SceneVisibility
from ui.canvas_infra.scene.models import CanvasSceneGraph
from ui.canvas_infra.scene.stacking_policy import CanvasStackLayer, CanvasStackRole
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

from .scene_objects import MagnifierCircle, MagnifierSceneObject

MAGNIFIER_Z_ORDER = CanvasFeatureZOrder(
    stack_role=CanvasStackRole.IMAGE_OVERLAY_CONTENT,
    active_bias=True,
    selectable_when_hidden=True,
)


def clamp_capture_position(
    rel_x: float,
    rel_y: float,
    pix_w: int,
    pix_h: int,
    capture_size_relative: float,
):
    if pix_w <= 0 or pix_h <= 0:
        return rel_x, rel_y
    ref_dim = math.sqrt(float(pix_w) * float(pix_h))
    capture_size_px = capture_size_relative * ref_dim
    radius_rel_x = (capture_size_px / 2.0) / pix_w if pix_w > 0 else 0.0
    radius_rel_y = (capture_size_px / 2.0) / pix_h if pix_h > 0 else 0.0
    return (
        max(radius_rel_x, min(rel_x, 1.0 - radius_rel_x)),
        max(radius_rel_y, min(rel_y, 1.0 - radius_rel_y)),
    )


def clamp_capture_overlay_geometry(
    *,
    bounds: Rect,
    center_x: float,
    center_y: float,
    radius: float,
):
    if bounds.w <= 0 or bounds.h <= 0 or radius <= 0:
        return center_x, center_y, max(0.0, radius)

    left = float(bounds.x)
    top = float(bounds.y)
    right = float(bounds.x + bounds.w)
    bottom = float(bounds.y + bounds.h)

    max_radius_x = max(0.0, (right - left) / 2.0)
    max_radius_y = max(0.0, (bottom - top) / 2.0)
    clamped_radius = min(radius, max_radius_x, max_radius_y)

    clamped_x = min(max(center_x, left + clamped_radius), right - clamped_radius)
    clamped_y = min(max(center_y, top + clamped_radius), bottom - clamped_radius)
    return clamped_x, clamped_y, clamped_radius


def build_magnifier_object(
    *,
    context: CanvasSceneBuildContext,
    model,
    z_index: int,
    is_active: bool,
):
    store = context.store
    image_label = context.image_label
    bounds = context.bounds
    pix_w = context.pix_w
    pix_h = context.pix_h
    view = store.viewport.view_state
    interaction = getattr(store.viewport, "interaction_state", None)
    _get_capture_state = get_canvas_feature_command_by_alias("capture.widget_state")
    capture_state = _get_capture_state(view) if _get_capture_state is not None else None
    diff_mode = getattr(view, "diff_mode", "off")
    is_visual_diff = diff_mode in ("highlight", "grayscale", "ssim", "edges")
    use_visual_motion = bool(
        is_active
        and interaction
        and getattr(interaction, "is_interactive_mode", False)
        and getattr(view, "optimize_interactive_movement", True)
    )
    effective_offset = (
        getattr(interaction, "interactive_offset_relative_visual", None)
        if use_visual_motion
        else None
    ) or model.offset_relative
    effective_spacing = (
        float(
            getattr(
                interaction,
                "interactive_spacing_relative_visual",
                model.spacing_relative,
            )
        )
        if use_visual_motion
        else float(model.spacing_relative)
    )
    effective_internal_split = (
        float(
            getattr(
                interaction, "interactive_internal_split_visual", model.internal_split
            )
        )
        if use_visual_motion
        else float(model.internal_split)
    )

    rel_x, rel_y = clamp_capture_position(
        model.position.x,
        model.position.y,
        pix_w,
        pix_h,
        model.capture_size_relative,
    )
    capture_size_px = model.capture_size_relative * math.sqrt(
        float(pix_w) * float(pix_h)
    )
    capture_radius = capture_size_px / 2.0

    center_x = bounds.x + (rel_x * pix_w)
    center_y = bounds.y + (rel_y * pix_h)

    center_x, center_y, capture_radius = clamp_capture_overlay_geometry(
        bounds=bounds,
        center_x=center_x,
        center_y=center_y,
        radius=capture_radius,
    )

    capture_center = Point(center_x, center_y)
    target_max_dim = math.sqrt(float(pix_w) * float(pix_h))
    mag_radius = max(0.0, (model.size_relative * target_max_dim) / 2.0)

    if model.freeze and model.frozen_position is not None:
        frozen_x, frozen_y = clamp_capture_position(
            model.frozen_position.x,
            model.frozen_position.y,
            pix_w,
            pix_h,
            model.capture_size_relative,
        )
        base_x = bounds.x + (frozen_x * pix_w)
        base_y = bounds.y + (frozen_y * pix_h)
        base_x, base_y, _ = clamp_capture_overlay_geometry(
            bounds=bounds,
            center_x=base_x,
            center_y=base_y,
            radius=capture_radius,
        )
    else:
        base_x = capture_center.x
        base_y = capture_center.y

    base_mag_x = base_x + (effective_offset.x * target_max_dim)
    base_mag_y = base_y + (effective_offset.y * target_max_dim)

    circles: list[MagnifierCircle] = []
    is_combined = bool(
        model.visible_left
        and model.visible_right
        and effective_spacing <= THRESHOLD + 1e-5
    )

    if is_combined:
        if is_visual_diff and model.visible_center:
            if not model.is_horizontal:
                if model.visible_center:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x, base_mag_y - mag_radius - 4),
                            mag_radius,
                            "diff",
                        )
                    )
                if model.visible_left or model.visible_right:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x, base_mag_y + mag_radius + 4),
                            mag_radius,
                            "combined",
                        )
                    )
            else:
                if model.visible_center:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x - mag_radius - 4, base_mag_y),
                            mag_radius,
                            "diff",
                        )
                    )
                if model.visible_left or model.visible_right:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x + mag_radius + 4, base_mag_y),
                            mag_radius,
                            "combined",
                        )
                    )
        elif model.visible_left or model.visible_right:
            role = (
                "combined"
                if model.visible_left and model.visible_right
                else ("left" if model.visible_left else "right")
            )
            circles.append(
                MagnifierCircle(Point(base_mag_x, base_mag_y), mag_radius, role)
            )
    else:
        spacing_px = effective_spacing * target_max_dim
        dist = mag_radius + (spacing_px / 2.0)
        if not model.is_horizontal:
            left_circle = MagnifierCircle(
                Point(base_mag_x - dist, base_mag_y), mag_radius, "left"
            )
            right_circle = MagnifierCircle(
                Point(base_mag_x + dist, base_mag_y), mag_radius, "right"
            )
        else:
            left_circle = MagnifierCircle(
                Point(base_mag_x, base_mag_y - dist), mag_radius, "left"
            )
            right_circle = MagnifierCircle(
                Point(base_mag_x, base_mag_y + dist), mag_radius, "right"
            )

        if is_visual_diff:
            offset_3 = max(mag_radius * 2.0, mag_radius * 2.0 + spacing_px)
            if not model.is_horizontal:
                if model.visible_left:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x - offset_3, base_mag_y), mag_radius, "left"
                        )
                    )
                if model.visible_right:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x + offset_3, base_mag_y),
                            mag_radius,
                            "right",
                        )
                    )
            else:
                if model.visible_left:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x, base_mag_y - offset_3), mag_radius, "left"
                        )
                    )
                if model.visible_right:
                    circles.append(
                        MagnifierCircle(
                            Point(base_mag_x, base_mag_y + offset_3),
                            mag_radius,
                            "right",
                        )
                    )
            if model.visible_center:
                circles.append(
                    MagnifierCircle(Point(base_mag_x, base_mag_y), mag_radius, "center")
                )
        else:
            if model.visible_left:
                circles.append(left_circle)
            if model.visible_right:
                circles.append(right_circle)

    interactive_index = None
    if is_combined and circles:
        if is_visual_diff and model.visible_center and len(circles) >= 2:
            interactive_index = 1
        else:
            interactive_index = 0
    elif len(circles) == 1:
        interactive_index = 0

    return MagnifierSceneObject(
        id=model.id,
        kind="magnifier",
        visible=bool(model.visible),
        z_index=z_index,
        stack_hint=MAGNIFIER_Z_ORDER.stack_hint(
            layer=(
                CanvasStackLayer.OBJECT_ACTIVE if is_active else CanvasStackLayer.OBJECT
            ),
            priority=z_index,
        ),
        source_position=Point(rel_x, rel_y),
        source_radius=capture_radius,
        capture_center=capture_center if model.show_capture_area else None,
        capture_radius=capture_radius if model.show_capture_area else 0.0,
        circles=tuple(circles),
        interactive_circle_index=interactive_index,
        internal_split=effective_internal_split,
        is_horizontal=bool(model.is_horizontal),
        is_combined=is_combined,
        divider_visible=bool(model.divider_visible),
        divider_thickness=int(model.divider_thickness),
        border_thickness=int(model.border_thickness),
        divider_color=model.divider_color,
        border_color=model.border_color,
        capture_color=(
            getattr(model, "capture_color", None)
            or getattr(model, "capture_ring_color", None)
            or (capture_state.color if capture_state is not None else Color())
        ),
        guides_color=(
            getattr(model, "guides_color", None) or getattr(model, "laser_color", None)
        ),
        show_laser=bool(getattr(model, "show_laser", True)),
    )


def build_magnifier_objects(
    context: CanvasSceneBuildContext,
) -> tuple[MagnifierSceneObject, ...]:
    view = context.store.viewport.view_state
    render = context.store.viewport.render_config
    models = iter_magnifier_models(view, render)
    active_id = active_magnifier_id(view)
    total_models = len(models)
    return tuple(
        build_magnifier_object(
            context=context,
            model=model,
            z_index=(total_models + index) if model.id == active_id else index,
            is_active=model.id == active_id,
        )
        for index, model in enumerate(models)
    )


def _distance_squared(point: Point, circle: MagnifierCircle) -> float:
    dx = point.x - circle.center.x
    dy = point.y - circle.center.y
    return (dx * dx) + (dy * dy)


def circle_contains(circle: MagnifierCircle, point: Point) -> bool:
    if not circle.visible or circle.radius <= 0:
        return False
    return _distance_squared(point, circle) <= (circle.radius * circle.radius)


def _capture_contains(obj: MagnifierSceneObject, point: Point) -> bool:
    if obj.capture_center is None or obj.capture_radius <= 0:
        return False
    capture_circle = MagnifierCircle(
        center=obj.capture_center,
        radius=obj.capture_radius,
        role="capture",
        visible=True,
    )
    return circle_contains(capture_circle, point)


def find_magnifier_at_position(
    scene: CanvasSceneGraph,
    point: Point,
) -> MagnifierSceneObject | None:
    candidates = [
        obj
        for obj in scene.iter_pick_objects(kind="magnifier")
        if isinstance(obj, MagnifierSceneObject)
    ]
    best_match = None
    best_distance = None
    for obj in candidates:
        if _capture_contains(obj, point):
            distance = _distance_squared(
                point,
                MagnifierCircle(
                    center=obj.capture_center,
                    radius=obj.capture_radius,
                    role="capture",
                    visible=True,
                ),
            )
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = obj
        for circle in obj.circles:
            if not circle_contains(circle, point):
                continue
            distance = _distance_squared(point, circle)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_match = obj
    return best_match


def get_active_magnifier(scene: CanvasSceneGraph) -> MagnifierSceneObject | None:
    active = scene.get_object(scene.active_object_id)
    if isinstance(active, MagnifierSceneObject) and active.visible:
        return active
    for obj in scene.iter_objects(kind="magnifier"):
        if isinstance(obj, MagnifierSceneObject) and obj.visible:
            return obj
    return None


def _normalize_arc_deg(start_deg: float, end_deg: float) -> list[tuple[float, float]]:
    start = start_deg % 360.0
    end = end_deg % 360.0
    if math.isclose(start, end, abs_tol=1e-9):
        return [(0.0, 360.0)]
    if start <= end:
        return [(start, end)]
    return [(start, 360.0), (0.0, end)]


def _merge_arc_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not ranges:
        return []
    ordered = sorted(ranges, key=lambda item: item[0])
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        last = merged[-1]
        if start <= last[1] + 1e-6:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    if len(merged) >= 2 and merged[0][0] <= 1e-6 and merged[-1][1] >= 360.0 - 1e-6:
        wrapped = [merged[-1][0] - 360.0, merged[0][1]]
        middle = merged[1:-1]
        merged = [wrapped] + middle
    return [(start, end) for start, end in merged]


def _compute_occluded_capture_arcs(
    all_magnifiers: list[MagnifierSceneObject],
    visible_magnifiers: list[MagnifierSceneObject],
    active_object_id: str | None,
) -> list[tuple[QPointF, float, float, float, bool]]:
    arcs: list[tuple[QPointF, float, float, float, bool]] = []

    for obj in visible_magnifiers:
        center = getattr(obj, "capture_center", None)
        radius = float(getattr(obj, "capture_radius", 0.0) or 0.0)
        if center is None or radius <= 0:
            continue
        ranges: list[tuple[float, float]] = []
        cx = float(center.x)
        cy = float(center.y)
        for other in visible_magnifiers:
            for circle in getattr(other, "circles", ()) or ():
                if circle.center is None or circle.radius <= 0 or not circle.visible:
                    continue
                ox = float(circle.center.x)
                oy = float(circle.center.y)
                oradius = float(circle.radius)
                dx = ox - cx
                dy = oy - cy
                distance = math.hypot(dx, dy)
                if distance <= 1e-6:
                    if oradius >= radius - 1e-6:
                        ranges = [(0.0, 360.0)]
                        break
                    continue
                if distance >= radius + oradius - 1e-6:
                    continue
                if distance + radius <= oradius + 1e-6:
                    ranges = [(0.0, 360.0)]
                    break
                cosine = (distance * distance + radius * radius - oradius * oradius) / (
                    2.0 * distance * radius
                )
                cosine = max(-1.0, min(1.0, cosine))
                half_angle = math.degrees(math.acos(cosine))

                center_angle = math.degrees(math.atan2(-dy, dx))
                ranges.extend(
                    _normalize_arc_deg(
                        center_angle - half_angle, center_angle + half_angle
                    )
                )
            if ranges == [(0.0, 360.0)]:
                break
        for start_deg, end_deg in _merge_arc_ranges(ranges):
            span_deg = end_deg - start_deg
            if span_deg <= 0.25:
                continue
            arcs.append(
                (
                    QPointF(cx, cy),
                    radius,
                    start_deg,
                    span_deg,
                    obj.id == active_object_id,
                )
            )
    return arcs


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
    _get_capture_state_fn = get_canvas_feature_command_by_alias("capture.widget_state")
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
        occluded_capture_arcs = _compute_occluded_capture_arcs(
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


def sync_active_magnifier_geometry(scene: CanvasSceneGraph, geometry_state) -> None:
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
