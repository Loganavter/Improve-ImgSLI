import logging

from OpenGL import GL as gl
from PIL import Image as PilImage
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QImage, QPixmap

logger = logging.getLogger("ImproveImgSLI")

def _upload_pil_to_texture_id(widget, pil_image, texture_id: int, slot_index: int | None = None):
    if pil_image is None or not texture_id:
        return

    widget.makeCurrent()
    img = pil_image.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        img.width,
        img.height,
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        raw,
    )
    if slot_index is not None and 0 <= slot_index < len(widget._images_uploaded):
        widget._images_uploaded[slot_index] = True

def upload_image(widget, qimage: QImage, slot_index: int):
    if slot_index not in (0, 1) or qimage.isNull():
        return

    widget._images_uploaded[slot_index] = True
    widget.makeCurrent()

    converted_img = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = converted_img.constBits()
    ptr.setsize(converted_img.sizeInBytes())

    gl.glBindTexture(gl.GL_TEXTURE_2D, widget.texture_ids[slot_index])
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        converted_img.width(),
        converted_img.height(),
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        bytes(ptr),
    )
    widget.update()

def upload_source_pil_image(widget, pil_image, slot_index: int):
    if slot_index not in (0, 1) or pil_image is None:
        return

    texture_id = widget._source_texture_ids[slot_index] if slot_index < len(widget._source_texture_ids) else 0
    if not texture_id:
        return

    widget.makeCurrent()
    img = pil_image.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        img.width,
        img.height,
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        raw,
    )

def letterbox_pil(widget, img: PilImage.Image, slot_index: int = -1) -> PilImage.Image:
    cw, ch = widget.width(), widget.height()
    if cw <= 0 or ch <= 0:
        if slot_index >= 0:
            widget._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
        return img.convert("RGBA")

    img = img.convert("RGBA")
    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:
        widget._letterbox_params[slot_index] = (
            (cw - nw) / (2.0 * cw),
            (ch - nh) / (2.0 * ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            widget._content_rect_px = (offset_x, offset_y, nw, nh)
    scaled = img.resize((nw, nh), PilImage.Resampling.BILINEAR)
    result = PilImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
    result.paste(scaled, (offset_x, offset_y))
    return result

def update_letterbox_geometry(widget, img: PilImage.Image | None, slot_index: int = -1):
    cw, ch = widget.width(), widget.height()
    if img is None or cw <= 0 or ch <= 0 or img.width <= 0 or img.height <= 0:
        if slot_index >= 0:
            widget._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
            if slot_index == 0:
                widget._content_rect_px = (0, 0, max(1, cw), max(1, ch))
        return

    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:
        widget._letterbox_params[slot_index] = (
            (cw - nw) / (2.0 * cw),
            (ch - nh) / (2.0 * ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            widget._content_rect_px = (offset_x, offset_y, nw, nh)

def upload_pil_images(
    widget,
    pil_image1,
    pil_image2,
    source_image1=None,
    source_image2=None,
    source_key=None,
    shader_letterbox: bool = False,
):
    widget._stored_pil_images = [pil_image1, pil_image2]
    widget._shader_letterbox_mode = bool(shader_letterbox)
    has_explicit_source = source_image1 is not None and source_image2 is not None
    if has_explicit_source:
        source_ids = (
            source_key
            if source_key is not None
            else [
                id(source_image1) if source_image1 is not None else 0,
                id(source_image2) if source_image2 is not None else 0,
            ]
        )
        source_changed = source_ids != getattr(widget, "_source_image_ids", None)
        widget._source_pil_images = [source_image1, source_image2]
        widget._source_image_ids = source_ids
        if source_changed:
            widget._source_images_ready = False
    else:
        source_changed = getattr(widget, "_source_image_ids", None) is not None
        widget._source_pil_images = [None, None]
        widget._source_image_ids = None
        widget._source_images_ready = False
    if pil_image1:
        if widget._shader_letterbox_mode:
            update_letterbox_geometry(widget, pil_image1, slot_index=0)
            _upload_pil_to_texture_id(widget, pil_image1, widget.texture_ids[0], slot_index=0)
        else:
            lb1 = letterbox_pil(widget, pil_image1, slot_index=0)
            _upload_pil_to_texture_id(widget, lb1, widget.texture_ids[0], slot_index=0)
    if pil_image2:
        if widget._shader_letterbox_mode:
            update_letterbox_geometry(widget, pil_image2, slot_index=1)
            _upload_pil_to_texture_id(widget, pil_image2, widget.texture_ids[1], slot_index=1)
        else:
            lb2 = letterbox_pil(widget, pil_image2, slot_index=1)
            _upload_pil_to_texture_id(widget, lb2, widget.texture_ids[1], slot_index=1)
    if has_explicit_source:
        try:
            if source_changed or not getattr(widget, "_source_images_ready", False):
                if source_image1 is not None:
                    upload_source_pil_image(widget, source_image1, 0)
                if source_image2 is not None:
                    upload_source_pil_image(widget, source_image2, 1)
                widget._source_images_ready = True
        except Exception:
            widget._source_images_ready = False
            if hasattr(widget, "_schedule_source_preload"):
                widget._schedule_source_preload()
    widget.update()

def set_background(widget, pixmap: QPixmap | None):
    widget._background_pixmap = pixmap
    if pixmap:
        upload_image(widget, pixmap.toImage(), 0)
    widget.update()

def set_magnifier_content(widget, pixmap: QPixmap | None, top_left: QPoint | None):
    widget._magnifier_pixmap = pixmap
    widget._magnifier_top_left = top_left

    if pixmap is None or pixmap.isNull() or top_left is None or not widget._mag_tex_ids[0]:
        widget._mag_quads[0] = None
        widget._mag_quads[1] = None
        widget._mag_quads[2] = None
        widget._mag_combined_params[0] = None
        widget._mag_combined_params[1] = None
        widget._mag_combined_params[2] = None
        widget._mag_quad_ndc = None
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
        widget._mag_quads[0] = (x0, y0, x1, y1, cx, cy, r)
        widget._mag_use_circle_mask[0] = False
        widget._mag_quad_ndc = (x0, y0, x1, y1)
    else:
        widget._mag_quads[0] = None
        widget._mag_quad_ndc = None

    widget._mag_quads[1] = None
    widget._mag_quads[2] = None
    widget._mag_combined_params[0] = None
    widget._mag_combined_params[1] = None
    widget._mag_combined_params[2] = None
    widget._request_update()

def get_letterbox_params(widget, slot: int = 0) -> tuple:
    if slot < len(widget._letterbox_params) and widget._letterbox_params[slot]:
        return widget._letterbox_params[slot]
    img = widget._stored_pil_images[slot] if slot < len(widget._stored_pil_images) else None
    w, h = widget.width(), widget.height()
    if img and w > 0 and h > 0:
        ratio = min(w / img.width, h / img.height)
        nw = max(1, int(img.width * ratio))
        nh = max(1, int(img.height * ratio))
        return ((w - nw) / (2.0 * w), (h - nh) / (2.0 * h), nw / float(w), nh / float(h))
    return (0.0, 0.0, 1.0, 1.0)

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
    widget._mag_gpu_active = True
    widget._mag_gpu_channel_mode = channel_mode
    widget._mag_gpu_diff_mode = diff_mode
    widget._mag_gpu_diff_threshold = diff_threshold
    widget._mag_gpu_interp_mode = interp_mode

    w, h = widget.width(), widget.height()
    for i in range(3):
        slot = slots[i] if i < len(slots) else None
        widget._mag_gpu_slots[i] = slot
        if slot and w > 0 and h > 0:
            cx, cy = slot["center"].x(), slot["center"].y()
            r = slot["radius"]
            x0 = ((cx - r) / w) * 2.0 - 1.0
            x1 = ((cx + r) / w) * 2.0 - 1.0
            y1 = 1.0 - ((cy - r) / h) * 2.0
            y0 = 1.0 - ((cy + r) / h) * 2.0
            widget._mag_quads[i] = (x0, y0, x1, y1, cx, cy, r)
        else:
            widget._mag_quads[i] = None

    widget._magnifier_radius = slots[0]["radius"] if slots and slots[0] else 0
    if border_color is not None:
        widget._magnifier_border_color = border_color
    widget._magnifier_border_width = border_width
    widget._request_update()

def set_texture_filter(widget, texture_id: int, gl_filter: int):
    if not texture_id:
        return
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl_filter)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl_filter)

def clear_magnifier_gpu(widget):
    widget._mag_gpu_active = False
    for i in range(3):
        widget._mag_gpu_slots[i] = None
        widget._mag_quads[i] = None
        widget._mag_combined_params[i] = None
        widget._mag_use_circle_mask[i] = False
    widget._mag_quad_ndc = None
    widget._magnifier_pixmap = None
    widget._magnifier_top_left = None
    widget._capture_center = None
    widget._capture_radius = 0
    widget._magnifier_centers = []
    widget._magnifier_radius = 0
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
    if index < 0 or index > 2:
        return
    tid = widget._mag_tex_ids[index] if index < len(widget._mag_tex_ids) else 0
    if pil_image is None or not tid:
        widget._mag_quads[index] = None
        if index == 0:
            widget._mag_quad_ndc = None
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
        widget._mag_quads[index] = (x0, y0, x1, y1, cx, cy, radius)
        if index == 0:
            widget._mag_quad_ndc = (x0, y0, x1, y1)
    else:
        widget._mag_quads[index] = None
        if index == 0:
            widget._mag_quad_ndc = None

    widget._mag_use_circle_mask[index] = True
    widget._mag_combined_params[index] = None
    widget._magnifier_radius = radius
    if border_color is not None:
        widget._magnifier_border_color = border_color
    widget._magnifier_border_width = border_width
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
    divider_color: tuple = (1.0, 1.0, 1.0, 0.9),
    divider_thickness: int = 2,
    border_color: QColor | None = None,
    border_width: float = 2.0,
    index: int = 0,
    gl_filter: int = None,
):
    if index < 0 or index > 2:
        return
    tid1 = widget._mag_tex_ids[index] if index < len(widget._mag_tex_ids) else 0
    tid2 = widget._mag_combined_tex_ids[index] if index < len(widget._mag_combined_tex_ids) else 0
    if pil1 is None or pil2 is None or not tid1 or not tid2:
        widget._mag_quads[index] = None
        widget._mag_combined_params[index] = None
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
        widget._mag_quads[index] = (x0, y0_ndc, x1, y1_ndc, cx, cy, radius)
    else:
        widget._mag_quads[index] = None

    mag_px = int(radius * 2)
    div_thickness_uv = (divider_thickness / mag_px) * 0.5 if mag_px > 0 else 0.005
    widget._mag_combined_params[index] = {
        "split": split,
        "horizontal": horizontal,
        "divider_visible": divider_visible,
        "divider_color": divider_color,
        "divider_thickness_uv": div_thickness_uv,
    }
    widget._mag_use_circle_mask[index] = True
    widget._magnifier_radius = radius
    if border_color is not None:
        widget._magnifier_border_color = border_color
    widget._magnifier_border_width = border_width
    widget.update()

def set_layers(widget, background: QPixmap | None, magnifier: QPixmap | None, mag_pos: QPoint | None, coords_snapshot=None):
    if background is not None:
        set_background(widget, background)
    else:
        widget._background_pixmap = None
    set_magnifier_content(widget, magnifier, mag_pos)

def set_pil_layers(
    widget,
    pil_image1=None,
    pil_image2=None,
    magnifier=None,
    mag_pos=None,
    source_image1=None,
    source_image2=None,
    source_key=None,
    shader_letterbox: bool = False,
):
    if pil_image1 and pil_image2:
        upload_pil_images(
            widget,
            pil_image1,
            pil_image2,
            source_image1,
            source_image2,
            source_key,
            shader_letterbox=shader_letterbox,
        )

    if magnifier:
        pixmap = QPixmap.fromImage(
            QImage(
                magnifier.tobytes("raw", "RGBA"),
                magnifier.width,
                magnifier.height,
                QImage.Format.Format_RGBA8888,
            )
        )
        set_magnifier_content(widget, pixmap, mag_pos)
    else:
        widget.update()

def set_pixmap(widget, pixmap: QPixmap | None):
    if pixmap:
        qimage = pixmap.toImage()
        widget._store = None
        upload_image(widget, qimage, 0)
        upload_image(widget, qimage, 1)
        widget._background_pixmap = pixmap
        widget._stored_pil_images = [None, None]
        widget._source_pil_images = [None, None]
        widget._source_image_ids = [0, 0]
        widget._source_images_ready = False
        clear_magnifier_gpu(widget)
        widget._capture_center = None
        widget._capture_radius = 0
        widget._magnifier_centers = []
        widget._magnifier_radius = 0
        widget._show_divider = False
        widget._content_rect_px = (0, 0, max(1, pixmap.width()), max(1, pixmap.height()))
        widget._clip_overlays_to_content_rect = False
    else:
        set_layers(widget, None, None, None, None)

def clear(widget):
    widget._background_pixmap = None
    widget._magnifier_pixmap = None
    for i in range(2):
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget.texture_ids[i])
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D,
            0,
            gl.GL_RGBA,
            1,
            1,
            0,
            gl.GL_RGBA,
            gl.GL_UNSIGNED_BYTE,
            b"\x00\x00\x00\x00",
        )
    widget.update()
