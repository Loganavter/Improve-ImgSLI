from __future__ import annotations

import math

from domain.types import Color, Point
from tabs.image_compare.canvas.features.magnifier.constants import (
    MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE as THRESHOLD,
)
from tabs.image_compare.canvas.features.magnifier.state.store import (
    active_magnifier_id,
    iter_magnifier_models,
)
from tabs.image_compare.canvas.registry import registry
from ui.canvas_infra.scene.context import CanvasSceneBuildContext
from ui.canvas_infra.scene.feature_contract import CanvasFeatureZOrder
from ui.canvas_infra.scene.stacking_policy import CanvasStackLayer, CanvasStackRole

from tabs.image_compare.canvas.features.magnifier.geometry.core import clamp_capture_overlay_geometry, clamp_capture_position
from tabs.image_compare.canvas.features.magnifier.scene.objects import MagnifierCircle, MagnifierSceneObject

MAGNIFIER_Z_ORDER = CanvasFeatureZOrder(
    stack_role=CanvasStackRole.IMAGE_OVERLAY_CONTENT,
    active_bias=True,
    selectable_when_hidden=True,
)


def build_magnifier_object(
    *,
    context: CanvasSceneBuildContext,
    model,
    z_index: int,
    is_active: bool,
):
    store = context.store
    bounds = context.bounds
    pix_w = context.pix_w
    pix_h = context.pix_h
    view = store.viewport.view_state
    interaction = getattr(store.viewport, "interaction_state", None)
    _get_capture_state = registry().get_feature_command_by_alias("capture.widget_state")
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
