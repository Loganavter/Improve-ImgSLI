from OpenGL import GL as gl
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QImage, QPixmap

from .common import ensure_magnifier_slot_capacity

def _slot_signature(slot):
    if not slot:
        return None
    center = slot.get("center")
    uv_rect = tuple(float(v) for v in (slot.get("uv_rect") or (0.0, 0.0, 0.0, 0.0)))
    uv_rect2 = tuple(float(v) for v in (slot.get("uv_rect2") or (0.0, 0.0, 0.0, 0.0)))
    divider_color = slot.get("divider_color")
    divider_color_sig = (
        tuple(float(v) for v in divider_color)
        if divider_color is not None
        else None
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

def set_magnifier_content(widget, pixmap: QPixmap | None, top_left: QPoint | None):
    state = widget.runtime_state
    state._magnifier_pixmap = pixmap
    state._magnifier_top_left = top_left

    if not widget._mag_tex_ids:
        ensure_magnifier_slot_capacity(widget, 1)

    if pixmap is None or pixmap.isNull() or top_left is None or not widget._mag_tex_ids or not widget._mag_tex_ids[0]:
        for i in range(len(state._mag_quads)):
            state._mag_quads[i] = None
        for i in range(len(state._mag_combined_params)):
            state._mag_combined_params[i] = None
        state._mag_quad_ndc = None
        widget._request_update()
        return

    widget.makeCurrent()
    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())

    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._mag_tex_ids[0])
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, qimg.width(), qimg.height(), 0,
        gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, bytes(ptr),
    )

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
        state._mag_quads[0] = (x0, y0, x1, y1, cx, cy, r)
        state._mag_use_circle_mask[0] = False
        state._mag_quad_ndc = (x0, y0, x1, y1)
    else:
        state._mag_quads[0] = None
        state._mag_quad_ndc = None

    for i in range(1, len(state._mag_quads)):
        state._mag_quads[i] = None
    for i in range(len(state._mag_combined_params)):
        state._mag_combined_params[i] = None
    widget._request_update()

def set_magnifier_gpu_params(
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
    previous_active_count = sum(1 for slot in state._mag_gpu_slots if slot)
    target_count = max(len(slots), len(state._mag_gpu_slots))
    incoming_slots_sig = tuple(
        _slot_signature(slots[i] if i < len(slots) else None)
        for i in range(target_count)
    )
    current_slots_sig = tuple(
        _slot_signature(state._mag_gpu_slots[i] if i < len(state._mag_gpu_slots) else None)
        for i in range(target_count)
    )
    if (
        bool(state._mag_gpu_active)
        and current_slots_sig == incoming_slots_sig
        and int(state._mag_gpu_channel_mode or 0) == int(channel_mode or 0)
        and int(state._mag_gpu_diff_mode or 0) == int(diff_mode or 0)
        and abs(float(state._mag_gpu_diff_threshold or 0.0) - float(diff_threshold or 0.0)) <= 1e-9
        and int(state._mag_gpu_interp_mode or 0) == int(interp_mode or 0)
        and state._magnifier_border_color == border_color
        and abs(float(state._magnifier_border_width or 0.0) - float(border_width or 0.0)) <= 1e-6
        and abs(float(state._magnifier_radius or 0.0) - float(slots[0]["radius"] if slots and slots[0] else 0.0)) <= 1e-6
    ):
        return
    if previous_active_count != len(slots):
        for i in range(len(state._mag_gpu_slots)):
            state._mag_gpu_slots[i] = None
            state._mag_quads[i] = None
            state._mag_combined_params[i] = None
            state._mag_use_circle_mask[i] = False
        state._mag_quad_ndc = None
        state._magnifier_pixmap = None
        state._magnifier_top_left = None
    ensure_magnifier_slot_capacity(widget, len(slots))
    state._mag_gpu_active = True
    state._mag_gpu_channel_mode = channel_mode
    state._mag_gpu_diff_mode = diff_mode
    state._mag_gpu_diff_threshold = diff_threshold
    state._mag_gpu_interp_mode = interp_mode

    w, h = widget.width(), widget.height()
    for i in range(len(state._mag_gpu_slots)):
        slot = slots[i] if i < len(slots) else None
        state._mag_gpu_slots[i] = slot
        if slot and w > 0 and h > 0:
            cx, cy = slot["center"].x(), slot["center"].y()
            r = slot["radius"]
            x0 = ((cx - r) / w) * 2.0 - 1.0
            x1 = ((cx + r) / w) * 2.0 - 1.0
            y1 = 1.0 - ((cy - r) / h) * 2.0
            y0 = 1.0 - ((cy + r) / h) * 2.0
            state._mag_quads[i] = (x0, y0, x1, y1, cx, cy, r)
        else:
            state._mag_quads[i] = None
            state._mag_combined_params[i] = None
            state._mag_use_circle_mask[i] = False

    state._magnifier_radius = slots[0]["radius"] if slots and slots[0] else 0
    if border_color is not None:
        state._magnifier_border_color = border_color
    state._magnifier_border_width = border_width
    widget._request_update()

def clear_magnifier_gpu(widget):
    state = widget.runtime_state
    state._mag_gpu_active = False
    for i in range(len(state._mag_gpu_slots)):
        state._mag_gpu_slots[i] = None
        state._mag_quads[i] = None
        state._mag_combined_params[i] = None
        state._mag_use_circle_mask[i] = False
    state._mag_quad_ndc = None
    state._magnifier_pixmap = None
    state._magnifier_top_left = None
    state._capture_center = None
    state._capture_radius = 0
    state._capture_circles = []
    state._guide_sets = []
    state._hidden_capture_circles = []
    state._occluded_capture_arcs = []
    state._hidden_magnifier_circles = []
    state._magnifier_centers = []
    state._magnifier_radius = 0
    widget._request_update()

def upload_magnifier_crop(
    widget,
    pil_image,
    center: QPointF,
    radius: float,
    border_color: QColor | None = None,
    border_width: float = 2.0,
    index: int = 0,
    gl_filter: int = None,
):
    state = widget.runtime_state
    if index < 0:
        return
    ensure_magnifier_slot_capacity(widget, index + 1)
    tid = widget._mag_tex_ids[index] if index < len(widget._mag_tex_ids) else 0
    if pil_image is None or not tid:
        state._mag_quads[index] = None
        if index == 0:
            state._mag_quad_ndc = None
        widget.update()
        return

    if gl_filter is None:
        gl_filter = gl.GL_LINEAR

    widget.makeCurrent()
    img = pil_image.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    gl.glBindTexture(gl.GL_TEXTURE_2D, tid)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl_filter)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl_filter)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, img.width, img.height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, raw)

    w, h = widget.width(), widget.height()
    if w > 0 and h > 0:
        cx, cy = center.x(), center.y()
        x0 = ((cx - radius) / w) * 2.0 - 1.0
        x1 = ((cx + radius) / w) * 2.0 - 1.0
        y1 = 1.0 - ((cy - radius) / h) * 2.0
        y0 = 1.0 - ((cy + radius) / h) * 2.0
        state._mag_quads[index] = (x0, y0, x1, y1, cx, cy, radius)
        if index == 0:
            state._mag_quad_ndc = (x0, y0, x1, y1)
    else:
        state._mag_quads[index] = None
        if index == 0:
            state._mag_quad_ndc = None

    state._mag_use_circle_mask[index] = True
    state._mag_combined_params[index] = None
    state._magnifier_radius = radius
    if border_color is not None:
        state._magnifier_border_color = border_color
    state._magnifier_border_width = border_width
    widget.update()

def upload_combined_magnifier(
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
    gl_filter: int = None,
):
    state = widget.runtime_state
    if index < 0:
        return
    ensure_magnifier_slot_capacity(widget, index + 1)
    tid1 = widget._mag_tex_ids[index] if index < len(widget._mag_tex_ids) else 0
    tid2 = widget._mag_combined_tex_ids[index] if index < len(widget._mag_combined_tex_ids) else 0
    if pil1 is None or pil2 is None or not tid1 or not tid2:
        state._mag_quads[index] = None
        state._mag_combined_params[index] = None
        widget.update()
        return

    if gl_filter is None:
        gl_filter = gl.GL_LINEAR

    widget.makeCurrent()
    for pil_img, tid in ((pil1, tid1), (pil2, tid2)):
        img = pil_img.convert("RGBA")
        raw = img.tobytes("raw", "RGBA")
        gl.glBindTexture(gl.GL_TEXTURE_2D, tid)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl_filter)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl_filter)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, img.width, img.height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, raw)

    w, h = widget.width(), widget.height()
    if w > 0 and h > 0:
        cx, cy = center.x(), center.y()
        x0 = ((cx - radius) / w) * 2.0 - 1.0
        x1 = ((cx + radius) / w) * 2.0 - 1.0
        y1_ndc = 1.0 - ((cy - radius) / h) * 2.0
        y0_ndc = 1.0 - ((cy + radius) / h) * 2.0
        state._mag_quads[index] = (x0, y0_ndc, x1, y1_ndc, cx, cy, radius)
    else:
        state._mag_quads[index] = None

    mag_px = int(radius * 2)
    div_thickness_uv = (divider_thickness / mag_px) * 0.5 if mag_px > 0 else 0.005
    if divider_color is None:
        viewport = getattr(state._store, "viewport", None)
        divider = None
        if viewport is not None:
            from ui.canvas_features.magnifier.store import active_or_default_divider_color

            divider = active_or_default_divider_color(viewport.view_state)
        if divider is not None and hasattr(divider, "r"):
            divider_color = (
                divider.r / 255.0,
                divider.g / 255.0,
                divider.b / 255.0,
                divider.a / 255.0,
            )
        else:
            divider_color = (1.0, 1.0, 1.0, 0.9)
    state._mag_combined_params[index] = {
        "split": split,
        "horizontal": horizontal,
        "divider_visible": divider_visible,
        "divider_color": divider_color,
        "divider_thickness_px": divider_thickness,
        "divider_thickness_uv": div_thickness_uv,
    }
    state._mag_use_circle_mask[index] = True
    state._magnifier_radius = radius
    if border_color is not None:
        state._magnifier_border_color = border_color
    state._magnifier_border_width = border_width
    widget.update()
