from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QImage, QPixmap

_DEFAULT_FILTER = 9729

from ui.widgets.canvas.texture_parts.common import (
    ensure_feature_overlay_slot_capacity,
)

_log = logging.getLogger("ImproveImgSLI.feature_overlay.gpu")


def _slot_signature(slot):
    if not slot:
        return None
    center = slot.get("center")
    uv_rect = tuple(float(v) for v in (slot.get("uv_rect") or (0.0, 0.0, 0.0, 0.0)))
    uv_rect2 = tuple(float(v) for v in (slot.get("uv_rect2") or (0.0, 0.0, 0.0, 0.0)))
    divider_color = slot.get("divider_color")
    divider_color_sig = (
        tuple(float(v) for v in divider_color) if divider_color is not None else None
    )
    return (
        round(float(center.x()), 4) if center is not None else None,
        round(float(center.y()), 4) if center is not None else None,
        round(float(slot.get("radius", 0.0) or 0.0), 4),
        int(slot.get("source", 0) or 0),
        bool(slot.get("is_combined", False)),
        round(float(slot.get("internal_split", 0.0) or 0.0), 4),
        bool(slot.get("horizontal", False)),
        bool(slot.get("divider_visible", False)),
        round(float(slot.get("divider_thickness_px", 0.0) or 0.0), 4),
        round(float(slot.get("divider_thickness_uv", 0.0) or 0.0), 6),
        divider_color_sig,
        uv_rect,
        uv_rect2,
        slot.get("border_color"),
        round(float(slot.get("border_width", 0.0) or 0.0), 4),
    )


def set_feature_overlay_content(
    widget, pixmap: QPixmap | None, top_left: QPoint | None
):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    overlay._pixmap = pixmap
    overlay._top_left = top_left

    if not widget._feature_overlay_tex_ids:
        ensure_feature_overlay_slot_capacity(widget, 1)

    if (
        pixmap is None
        or pixmap.isNull()
        or top_left is None
        or not widget._feature_overlay_tex_ids
        or not widget._feature_overlay_tex_ids[0]
    ):
        for i in range(len(overlay._quads)):
            overlay._quads[i] = None
        for i in range(len(overlay._combined_params)):
            overlay._combined_params[i] = None
        state._feature_overlay_quad_ndc = None
        widget._request_update()
        return

    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)

    _ = qimg

    w, h = widget.width(), widget.height()
    if w > 0 and h > 0:
        pw, ph = qimg.width(), qimg.height()
        x0 = (top_left.x() / w) * 2.0 - 1.0
        x1 = ((top_left.x() + pw) / w) * 2.0 - 1.0
        y1 = 1.0 - (top_left.y() / h) * 2.0
        y0 = 1.0 - ((top_left.y() + ph) / h) * 2.0
        cx = top_left.x() + pw / 2.0
        cy = top_left.y() + ph / 2.0
        r = max(pw, ph) / 2.0
        overlay._quads[0] = (x0, y0, x1, y1, cx, cy, r)
        overlay._use_circle_mask[0] = False
        state._feature_overlay_quad_ndc = (x0, y0, x1, y1)
    else:
        overlay._quads[0] = None
        state._feature_overlay_quad_ndc = None

    for i in range(1, len(overlay._quads)):
        overlay._quads[i] = None
    for i in range(len(overlay._combined_params)):
        overlay._combined_params[i] = None
    widget._request_update()


def set_feature_overlay_gpu_params(
    widget,
    slots,
    channel_mode=0,
    diff_mode=0,
    diff_threshold=20.0 / 255.0,
    border_color: QColor | None = None,
    border_width: float = 2.0,
    interp_mode: int = 1,
):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    target_count = max(len(slots), len(overlay._gpu_slots))
    incoming_slots_sig = tuple(
        _slot_signature(slots[i] if i < len(slots) else None)
        for i in range(target_count)
    )
    current_slots_sig = tuple(
        _slot_signature(overlay._gpu_slots[i] if i < len(overlay._gpu_slots) else None)
        for i in range(target_count)
    )
    if (
        bool(overlay._gpu_active)
        and current_slots_sig == incoming_slots_sig
        and int(overlay._gpu_channel_mode or 0) == int(channel_mode or 0)
        and int(overlay._gpu_diff_mode or 0) == int(diff_mode or 0)
        and abs(
            float(overlay._gpu_diff_threshold or 0.0) - float(diff_threshold or 0.0)
        )
        <= 1e-9
        and int(overlay._gpu_interp_mode or 0) == int(interp_mode or 0)
        and overlay._border_color == border_color
        and abs(float(overlay._border_width or 0.0) - float(border_width or 0.0))
        <= 1e-6
        and abs(
            float(overlay._radius or 0.0)
            - float(slots[0]["radius"] if slots and slots[0] else 0.0)
        )
        <= 1e-6
    ):
        return
    ensure_feature_overlay_slot_capacity(widget, len(slots))
    overlay._gpu_active = True
    overlay._gpu_channel_mode = channel_mode
    overlay._gpu_diff_mode = diff_mode
    overlay._gpu_diff_threshold = diff_threshold
    overlay._gpu_interp_mode = interp_mode

    w, h = widget.width(), widget.height()
    for i in range(len(overlay._gpu_slots)):
        slot = slots[i] if i < len(slots) else None
        old_slot = overlay._gpu_slots[i]
        if _slot_signature(old_slot) != _slot_signature(slot):
            overlay._combined_params[i] = None
        overlay._gpu_slots[i] = slot
        if slot and w > 0 and h > 0:
            cx, cy = slot["center"].x(), slot["center"].y()
            r = slot["radius"]
            x0 = ((cx - r) / w) * 2.0 - 1.0
            x1 = ((cx + r) / w) * 2.0 - 1.0
            y1 = 1.0 - ((cy - r) / h) * 2.0
            y0 = 1.0 - ((cy + r) / h) * 2.0
            overlay._quads[i] = (x0, y0, x1, y1, cx, cy, r)
        else:
            overlay._quads[i] = None
            overlay._combined_params[i] = None
            overlay._use_circle_mask[i] = False

    overlay._radius = slots[0]["radius"] if slots and slots[0] else 0
    if border_color is not None:
        overlay._border_color = border_color
    overlay._border_width = border_width
    widget._request_update()


def clear_feature_overlay_gpu(widget):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    overlay._gpu_active = False
    for i in range(len(overlay._gpu_slots)):
        overlay._gpu_slots[i] = None
        overlay._quads[i] = None
        overlay._combined_params[i] = None
        overlay._use_circle_mask[i] = False
    state._feature_overlay_quad_ndc = None
    overlay._pixmap = None
    overlay._top_left = None
    state._capture_center = None
    state._capture_radius = 0
    state._capture_circles = []
    state._guide_sets = []
    state._hidden_capture_circles = []
    state._occluded_capture_arcs = []
    state._hidden_overlay_circles = []
    overlay._centers = []
    overlay._radius = 0
    widget._request_update()


def upload_feature_overlay_crop(
    widget,
    pil_image,
    center: QPointF,
    radius: float,
    border_color: QColor | None = None,
    border_width: float = 2.0,
    index: int = 0,
    canvas_filter: int = None,
):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    if index < 0:
        return
    ensure_feature_overlay_slot_capacity(widget, index + 1)
    tid = (
        widget._feature_overlay_tex_ids[index]
        if index < len(widget._feature_overlay_tex_ids)
        else 0
    )
    if pil_image is None or not tid:
        overlay._quads[index] = None
        if index == 0:
            state._feature_overlay_quad_ndc = None
        widget.update()
        return

    if canvas_filter is None:
        canvas_filter = _DEFAULT_FILTER

    _ = pil_image.convert("RGBA")

    w, h = widget.width(), widget.height()
    if w > 0 and h > 0:
        cx, cy = center.x(), center.y()
        x0 = ((cx - radius) / w) * 2.0 - 1.0
        x1 = ((cx + radius) / w) * 2.0 - 1.0
        y1 = 1.0 - ((cy - radius) / h) * 2.0
        y0 = 1.0 - ((cy + radius) / h) * 2.0
        overlay._quads[index] = (x0, y0, x1, y1, cx, cy, radius)
        if index == 0:
            state._feature_overlay_quad_ndc = (x0, y0, x1, y1)
    else:
        overlay._quads[index] = None
        if index == 0:
            state._feature_overlay_quad_ndc = None

    overlay._use_circle_mask[index] = True
    overlay._combined_params[index] = None
    overlay._radius = radius
    if border_color is not None:
        overlay._border_color = border_color
    overlay._border_width = border_width
    widget.update()


def upload_feature_overlay_pair(
    widget,
    pil1,
    pil2,
    center: QPointF,
    radius: float,
    split: float = 0.5,
    horizontal: bool = False,
    divider_visible: bool = True,
    divider_color: tuple | None = None,
    divider_thickness: int = 2,
    border_color: QColor | None = None,
    border_width: float = 2.0,
    index: int = 0,
    canvas_filter: int = None,
):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    if index < 0:
        return
    ensure_feature_overlay_slot_capacity(widget, index + 1)
    tid1 = (
        widget._feature_overlay_tex_ids[index]
        if index < len(widget._feature_overlay_tex_ids)
        else 0
    )
    tid2 = (
        widget._feature_overlay_aux_tex_ids[index]
        if index < len(widget._feature_overlay_aux_tex_ids)
        else 0
    )
    if pil1 is None or pil2 is None or not tid1 or not tid2:
        overlay._quads[index] = None
        overlay._combined_params[index] = None
        widget.update()
        return

    if canvas_filter is None:
        canvas_filter = _DEFAULT_FILTER

    for pil_img in (pil1, pil2):
        _ = pil_img.convert("RGBA")

    w, h = widget.width(), widget.height()
    if w > 0 and h > 0:
        cx, cy = center.x(), center.y()
        x0 = ((cx - radius) / w) * 2.0 - 1.0
        x1 = ((cx + radius) / w) * 2.0 - 1.0
        y1_ndc = 1.0 - ((cy - radius) / h) * 2.0
        y0_ndc = 1.0 - ((cy + radius) / h) * 2.0
        overlay._quads[index] = (x0, y0_ndc, x1, y1_ndc, cx, cy, radius)
    else:
        overlay._quads[index] = None

    overlay_px = int(radius * 2)
    div_thickness_uv = (
        (divider_thickness / overlay_px) * 0.5 if overlay_px > 0 else 0.005
    )
    if divider_color is None:
        divider_color = (1.0, 1.0, 1.0, 0.9)
    overlay._combined_params[index] = {
        "split": split,
        "horizontal": horizontal,
        "divider_visible": divider_visible,
        "divider_color": divider_color,
        "divider_thickness_px": divider_thickness,
        "divider_thickness_uv": div_thickness_uv,
    }
    overlay._use_circle_mask[index] = True
    overlay._radius = radius
    if border_color is not None:
        overlay._border_color = border_color
    overlay._border_width = border_width
    widget.update()
