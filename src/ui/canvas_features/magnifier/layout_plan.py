from __future__ import annotations

import math
from dataclasses import replace

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.canvas_features.magnifier import DEFAULT_MAGNIFIER_ID, iter_magnifier_models
from ui.canvas_features.magnifier.constants import MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE as _COMBINE_THRESHOLD
from ui.canvas_features.magnifier.store import (
    active_magnifier_id,
    active_or_default_border_color,
)
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from ui.widgets.gl_canvas.render_metrics import resolve_relative_px
from ui.widgets.gl_canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS
from ui.canvas_presentation.plan import (
    CaptureCircle,
    GuideSet,
    OverlayLayout,
    OverlaySlot,
)

CAPTURE_RING_AA_PX = 1.15

def clamp_capture_position(
    rel_x: float, rel_y: float, width: int, height: int, capture_size: float
):
    ref_dim = math.sqrt(float(width) * float(height))
    radius_x = (capture_size * ref_dim / 2.0) / max(1.0, float(width))
    radius_y = (capture_size * ref_dim / 2.0) / max(1.0, float(height))
    return (
        max(radius_x, min(rel_x, 1.0 - radius_x)),
        max(radius_y, min(rel_y, 1.0 - radius_y)),
    )

def clamp_capture_overlay_geometry(
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    center_x: float,
    center_y: float,
    radius: float,
    stroke_margin: float,
):
    if width <= 0 or height <= 0 or radius <= 0:
        return center_x, center_y, max(0.0, radius)

    right = left + width
    bottom = top + height
    usable_left = left + stroke_margin
    usable_top = top + stroke_margin
    usable_right = right - stroke_margin
    usable_bottom = bottom - stroke_margin

    max_radius_x = max(0.0, (usable_right - usable_left) / 2.0)
    max_radius_y = max(0.0, (usable_bottom - usable_top) / 2.0)
    clamped_radius = min(radius, max_radius_x, max_radius_y)

    clamped_x = min(
        max(center_x, usable_left + clamped_radius),
        usable_right - clamped_radius,
    )
    clamped_y = min(
        max(center_y, usable_top + clamped_radius),
        usable_bottom - clamped_radius,
    )
    return clamped_x, clamped_y, clamped_radius

def build_magnifier_layout(
    vp,
    *,
    width: int,
    height: int,
    canvas_width: int,
    canvas_height: int,
    content_offset_x: float = 0.0,
    content_offset_y: float = 0.0,
    divider_thickness_px: int,
    render_scale: float = 1.0,
    border_width: float = 2.0,
    interpolation_method: str | None = None,
    diff_mode_override: int | None = None,
):
    view = vp.view_state
    render = vp.render_config
    capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
    _get_guides_state = get_canvas_feature_command_by_alias("guides.widget_state")
    guides_state = _get_guides_state(view) if _get_guides_state is not None else None
    visible_models = [
        model for model in iter_magnifier_models(view, render) if model.visible
    ]
    border = active_or_default_border_color(view)
    border_qcolor = QColor(border.r, border.g, border.b, border.a)
    if not visible_models:
        return None

    diff_mode = str(view.diff_mode or "off")
    diff_enabled = diff_mode in ("highlight", "grayscale", "ssim", "edges")
    target_max = math.sqrt(float(width) * float(height))
    active_id = active_magnifier_id(view) or DEFAULT_MAGNIFIER_ID
    active_model = next(
        (model for model in visible_models if model.id == active_id),
        visible_models[0],
    )
    draw_models = sorted(
        visible_models,
        key=lambda model: (model.id == active_id, model.id),
    )
    has_virtual_canvas_padding = (
        int(canvas_width) != int(width)
        or int(canvas_height) != int(height)
        or abs(float(content_offset_x)) > 1e-6
        or abs(float(content_offset_y)) > 1e-6
    )
    # Stroke thickness is referenced to the image-content short edge, not the
    # full virtual-canvas short edge. Otherwise uncrop padding grows the
    # canvas → makes the same model.border_thickness/divider_thickness draw
    # visually thicker than in the interactive view.
    canvas_short_edge = float(max(1, min(int(width), int(height))))
    local_scale = max(1e-6, float(render_scale or 1.0))
    divider_thickness_canvas_px = (
        resolve_relative_px(
            float(divider_thickness_px),
            short_edge_px=canvas_short_edge,
        )
        / local_scale
    )
    line_width_px = resolve_relative_px(
        DEFAULT_CANVAS_STYLE_TOKENS.capture_ring_stroke_du,
        short_edge_px=float(max(1, min(width, height))),
    )
    stroke_margin = ((line_width_px / 2.0) + CAPTURE_RING_AA_PX) / local_scale
    def _resolve_border_width_canvas_px(model) -> float:
        raw_width = float(
            getattr(model, "border_thickness", border_width) or border_width
        )
        return (
            resolve_relative_px(raw_width, short_edge_px=canvas_short_edge)
            / local_scale
        )

    def _capture_geometry(model):

        cap_x, cap_y = clamp_capture_position(
            model.position.x,
            model.position.y,
            width,
            height,
            model.capture_size_relative,
        )
        capture_ref = math.sqrt(float(width) * float(height))
        radius = (model.capture_size_relative * capture_ref) / 2.0
        center_x = float(content_offset_x) + (cap_x * width)
        center_y = float(content_offset_y) + (cap_y * height)
        # Always clamp to the image-content rect, not the full virtual canvas.
        # Clamping to the canvas (including padding) lets the capture rect
        # extend into the padded area outside the image pair — the user-
        # visible "capture goes outside the images" bug in uncrop mode.
        center_x, center_y, radius = clamp_capture_overlay_geometry(
            left=float(content_offset_x),
            top=float(content_offset_y),
            width=float(width),
            height=float(height),
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            stroke_margin=stroke_margin,
        )
        uv_half_w = radius / max(1.0, float(width))
        uv_half_h = radius / max(1.0, float(height))
        return cap_x, cap_y, center_x, center_y, radius, uv_half_w, uv_half_h

    (
        _active_cap_x,
        _active_cap_y,
        active_center_x,
        active_center_y,
        active_capture_radius,
        _,
        _,
    ) = _capture_geometry(active_model)

    def _make_slot(model, center_xy, source, radius, uv_rect, *, is_combined=False):
        local_x = center_xy[0] / render_scale
        local_y = center_xy[1] / render_scale
        local_radius = radius / render_scale
        local_mag_px = max(1.0, local_radius * 2.0)
        return OverlaySlot(
            center=QPointF(local_x, local_y),
            radius=local_radius,
            uv_rect=uv_rect,
            uv_rect2=uv_rect,
            source=source,
            is_combined=is_combined,
            internal_split=model.internal_split,
            horizontal=model.is_horizontal,
            divider_visible=bool(model.divider_visible),
            divider_color=(
                model.divider_color.r / 255.0,
                model.divider_color.g / 255.0,
                model.divider_color.b / 255.0,
                model.divider_color.a / 255.0,
            ),
            divider_thickness_uv=(divider_thickness_canvas_px / local_mag_px) * 0.5,
            border_color=QColor(
                model.border_color.r,
                model.border_color.g,
                model.border_color.b,
                model.border_color.a,
            ),
            border_width=_resolve_border_width_canvas_px(model),
        )

    slots: list[OverlaySlot] = []
    magnifier_centers: list[tuple[float, float]] = []
    capture_circles: list[CaptureCircle] = []
    guide_sets: list[GuideSet] = []
    mag_radius = 0.0

    for model in draw_models:
        (
            _cap_x,
            _cap_y,
            cap_center_x,
            cap_center_y,
            _cap_radius,
            uv_half_w,
            uv_half_h,
        ) = _capture_geometry(model)
        _cap_color = getattr(model, "capture_color", None) or capture_color
        capture_circles.append(
            CaptureCircle(
                center=QPointF(cap_center_x / render_scale, cap_center_y / render_scale),
                radius=_cap_radius / render_scale,
                color=QColor(
                    _cap_color.r,
                    _cap_color.g,
                    _cap_color.b,
                    _cap_color.a,
                ),
            )
        )
        uv_rect = (
            float(_cap_x - uv_half_w),
            float(_cap_y - uv_half_h),
            float(_cap_x + uv_half_w),
            float(_cap_y + uv_half_h),
        )
        radius = (model.size_relative * target_max) / 2.0
        mag_radius = max(mag_radius, radius)
        spacing_px = model.spacing_relative * target_max
        if model.freeze and model.frozen_position is not None:
            frozen_x, frozen_y = clamp_capture_position(
                model.frozen_position.x,
                model.frozen_position.y,
                width,
                height,
                model.capture_size_relative,
            )
            base_x = float(content_offset_x) + (frozen_x * width)
            base_y = float(content_offset_y) + (frozen_y * height)
        else:
            base_x = cap_center_x
            base_y = cap_center_y
        cx = base_x + (model.offset_relative.x * target_max)
        cy = base_y + (model.offset_relative.y * target_max)
        show_left = bool(model.visible_left)
        show_right = bool(model.visible_right)
        show_center = bool(model.visible_center)
        render_visual_diff = diff_enabled and show_center
        is_combined = (
            show_left
            and show_right
            and float(model.spacing_relative) <= _COMBINE_THRESHOLD + 1e-5
        )

        if is_combined:
            if render_visual_diff:
                if not model.is_horizontal:
                    diff_center = (cx, cy - radius - 4.0)
                    comb_center = (cx, cy + radius + 4.0)
                else:
                    diff_center = (cx - radius - 4.0, cy)
                    comb_center = (cx + radius + 4.0, cy)
                if show_center:
                    slots.append(_make_slot(model, diff_center, 2, radius, uv_rect))
                    magnifier_centers.append(diff_center)
                if show_left and show_right:
                    slots.append(
                        _make_slot(
                            model, comb_center, 0, radius, uv_rect, is_combined=True
                        )
                    )
                    magnifier_centers.append(comb_center)
                elif show_left:
                    slots.append(_make_slot(model, comb_center, 0, radius, uv_rect))
                    magnifier_centers.append(comb_center)
                elif show_right:
                    slots.append(_make_slot(model, comb_center, 1, radius, uv_rect))
                    magnifier_centers.append(comb_center)
            else:
                center = (cx, cy)
                if show_left and show_right:
                    slots.append(
                        _make_slot(model, center, 0, radius, uv_rect, is_combined=True)
                    )
                    magnifier_centers.append(center)
                elif show_left:
                    slots.append(_make_slot(model, center, 0, radius, uv_rect))
                    magnifier_centers.append(center)
                elif show_right:
                    slots.append(_make_slot(model, center, 1, radius, uv_rect))
                    magnifier_centers.append(center)
        elif render_visual_diff:
            offset_3 = max(radius * 2.0, radius * 2.0 + spacing_px)
            if not model.is_horizontal:
                left_center = (cx - offset_3, cy)
                right_center = (cx + offset_3, cy)
            else:
                left_center = (cx, cy - offset_3)
                right_center = (cx, cy + offset_3)
            if show_left:
                slots.append(_make_slot(model, left_center, 0, radius, uv_rect))
                magnifier_centers.append(left_center)
            if show_right:
                slots.append(_make_slot(model, right_center, 1, radius, uv_rect))
                magnifier_centers.append(right_center)
            if show_center:
                center = (cx, cy)
                slots.append(_make_slot(model, center, 2, radius, uv_rect))
                magnifier_centers.append(center)
        else:
            dist = radius + (spacing_px / 2.0)
            if not model.is_horizontal:
                left_center = (cx - dist, cy)
                right_center = (cx + dist, cy)
            else:
                left_center = (cx, cy - dist)
                right_center = (cx, cy + dist)
            if show_left and show_right:
                slots.append(_make_slot(model, left_center, 0, radius, uv_rect))
                slots.append(_make_slot(model, right_center, 1, radius, uv_rect))
                magnifier_centers.extend([left_center, right_center])
            elif show_left:
                slots.append(_make_slot(model, (cx, cy), 0, radius, uv_rect))
                magnifier_centers.append((cx, cy))
            elif show_right:
                slots.append(_make_slot(model, (cx, cy), 1, radius, uv_rect))
                magnifier_centers.append((cx, cy))

        local_target_centers = []
        if is_combined:
            if render_visual_diff:
                if show_center:
                    local_target_centers.append(diff_center)
                if show_left or show_right:
                    local_target_centers.append(comb_center)
            else:
                if show_left or show_right:
                    local_target_centers.append((cx, cy))
        elif render_visual_diff:
            if show_left:
                local_target_centers.append(left_center)
            if show_center:
                local_target_centers.append((cx, cy))
            if show_right:
                local_target_centers.append(right_center)
        else:
            if show_left and show_right:
                local_target_centers.extend([left_center, right_center])
            elif show_left:
                local_target_centers.append((cx, cy))
            elif show_right:
                local_target_centers.append((cx, cy))
        if local_target_centers and guides_state is not None and guides_state.enabled:
            guide_sets.append(
                GuideSet(
                    capture_center=QPointF(
                        cap_center_x / render_scale,
                        cap_center_y / render_scale,
                    ),
                    capture_radius=_cap_radius / render_scale,
                    target_centers=tuple(
                        QPointF(x / render_scale, y / render_scale)
                        for x, y in local_target_centers
                    ),
                    target_radii=tuple(
                        (radius / render_scale) for _ in local_target_centers
                    ),
                    color=(lambda c: QColor(c.r, c.g, c.b, c.a))(
                        getattr(model, "guides_color", None) or guides_state.color
                    ),
                )
            )

    interp_mode = {
        "NEAREST": 0,
        "BILINEAR": 1,
        "BICUBIC": 2,
        "LANCZOS": 3,
        "EWA_LANCZOS": 4,
    }.get(str(interpolation_method or render.interpolation_method or "BILINEAR").upper(), 1)

    return OverlayLayout(
        slots=tuple(slots),
        capture_circles=tuple(capture_circles),
        guide_sets=tuple(guide_sets),
        capture_center=QPointF(
            active_center_x / render_scale,
            active_center_y / render_scale,
        ),
        capture_radius=active_capture_radius / render_scale,
        overlay_centers=tuple(magnifier_centers),
        overlay_radius=mag_radius / render_scale,
        border_color=border_qcolor,
        border_width=resolve_relative_px(
            float(border_width),
            short_edge_px=canvas_short_edge,
        )
        / local_scale,
        channel_mode={"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
            view.channel_view_mode, 0
        ),
        interp_mode=interp_mode,
        diff_mode=(
            int(diff_mode_override)
            if diff_mode_override is not None
            else 4
            if diff_mode == "ssim"
            else {"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}.get(
                diff_mode, 0
            )
        ),
    )

def shift_layout_to_tile(
    layout: OverlayLayout,
    *,
    tile_left: float,
    tile_top: float,
) -> OverlayLayout:
    def shift_pt(pt: QPointF) -> QPointF:
        return QPointF(pt.x() - tile_left, pt.y() - tile_top)

    return replace(
        layout,
        slots=tuple(replace(slot, center=shift_pt(slot.center)) for slot in layout.slots),
        overlay_centers=tuple(
            (center_x - tile_left, center_y - tile_top)
            for center_x, center_y in layout.overlay_centers
        ),
        capture_center=shift_pt(layout.capture_center)
        if layout.capture_center is not None
        else None,
        capture_circles=tuple(
            replace(circle, center=shift_pt(circle.center))
            for circle in layout.capture_circles
        ),
        guide_sets=tuple(
            replace(
                guide,
                capture_center=shift_pt(guide.capture_center),
                target_centers=tuple(shift_pt(target) for target in guide.target_centers),
            )
            for guide in layout.guide_sets
        ),
    )
