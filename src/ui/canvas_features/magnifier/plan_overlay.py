from __future__ import annotations

from PyQt6.QtCore import QPointF

def _make_converters(canvas, plan):
    state = canvas.runtime_state
    content_rect = state._content_rect_px
    if not content_rect or plan.canvas_w <= 0 or plan.canvas_h <= 0:
        return None, None, None

    ox, oy, dw, dh = content_rect
    logical_w = max(1, int(plan.canvas_w))
    logical_h = max(1, int(plan.canvas_h))

    sx = dw / logical_w
    sy = dh / logical_h
    sr = min(sx, sy)

    def to_wx(cx: float) -> float:
        return ox + cx * sx

    def to_wy(cy: float) -> float:
        return oy + cy * sy

    def to_wr(r: float) -> float:
        return r * sr

    return to_wx, to_wy, to_wr

def _convert_point(pt, to_wx, to_wy) -> QPointF:
    return QPointF(to_wx(pt.x()), to_wy(pt.y()))

def _convert_tuple_point(cx, cy, to_wx, to_wy) -> QPointF:
    return QPointF(to_wx(cx), to_wy(cy))

def apply_magnifier_plan_overlay(canvas, plan) -> None:
    state = canvas.runtime_state
    layout = plan.overlay_layout
    if not layout or not layout.slots:
        canvas.clear_feature_overlay_gpu()
        return

    to_wx, to_wy, to_wr = _make_converters(canvas, plan)
    if to_wx is None:
        canvas.clear_feature_overlay_gpu()
        return

    converted_slots = []
    for slot in layout.slots:
        center = slot.center
        converted_slots.append(
            {
                "uv_rect": slot.uv_rect,
                "uv_rect2": slot.uv_rect2,
                "source": slot.source,
                "is_combined": slot.is_combined,
                "internal_split": slot.internal_split,
                "horizontal": slot.horizontal,
                "divider_visible": slot.divider_visible,
                "divider_color": slot.divider_color,
                "divider_thickness_uv": slot.divider_thickness_uv,
                "border_color": slot.border_color,
                "center": _convert_point(center, to_wx, to_wy),
                "radius": to_wr(float(slot.radius)),
                "border_width": to_wr(float(slot.border_width)),
            }
        )

    converted_circles = [
        (
            _convert_point(circle.center, to_wx, to_wy),
            to_wr(float(circle.radius)),
            circle.color,
        )
        for circle in layout.capture_circles
    ]

    converted_guides = []
    for guide in layout.guide_sets:
        conv_tr = tuple(to_wr(float(r)) for r in guide.target_radii)
        converted_guides.append(
            (
                _convert_point(guide.capture_center, to_wx, to_wy),
                to_wr(float(guide.capture_radius)),
                [_convert_point(target, to_wx, to_wy) for target in guide.target_centers],
                conv_tr,
                guide.color,
            )
        )

    raw_capture_center = layout.capture_center
    capture_radius = to_wr(float(layout.capture_radius))
    capture_center = (
        _convert_point(raw_capture_center, to_wx, to_wy)
        if raw_capture_center is not None
        else None
    )

    converted_overlay_centers = [
        _convert_tuple_point(cx, cy, to_wx, to_wy)
        for cx, cy in layout.overlay_centers
    ]
    overlay_radius = to_wr(float(layout.overlay_radius))

    effective_capture = (
        capture_center if (plan.capture_visible and capture_center is not None) else None
    )
    effective_cap_r = capture_radius if effective_capture is not None else 0.0

    canvas.set_overlay_coords(
        effective_capture,
        effective_cap_r,
        converted_overlay_centers,
        overlay_radius,
    )
    state._capture_circles = converted_circles
    state._guide_sets = converted_guides

    canvas.set_feature_overlay_gpu_params(
        converted_slots,
        layout.channel_mode,
        layout.diff_mode,
        20.0 / 255.0,
        layout.border_color,
        layout.border_width * state._content_sr,
        layout.interp_mode,
    )
