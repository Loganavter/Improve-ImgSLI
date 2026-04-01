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
    state = widget.runtime_state
    if slot_index is not None and 0 <= slot_index < len(state._images_uploaded):
        state._images_uploaded[slot_index] = True

def upload_image(widget, qimage: QImage, slot_index: int):
    state = widget.runtime_state
    if slot_index not in (0, 1) or qimage.isNull():
        return

    state._images_uploaded[slot_index] = True
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
    source_texture_ids = widget._source_texture_ids
    if slot_index not in (0, 1) or pil_image is None:
        return

    texture_id = source_texture_ids[slot_index] if slot_index < len(source_texture_ids) else 0
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

def upload_diff_source_pil_image(widget, pil_image):
    state = widget.runtime_state
    if pil_image is None or not widget._diff_source_texture_id:
        state._diff_source_pil_image = None
        state._diff_source_image_id = 0
        state._diff_source_ready = False
        return

    image_id = id(pil_image)
    if state._diff_source_ready and state._diff_source_image_id == image_id:
        return

    widget.makeCurrent()
    img = pil_image.convert("RGBA")
    raw = img.tobytes("raw", "RGBA")
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._diff_source_texture_id)
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
    state._diff_source_pil_image = pil_image
    state._diff_source_image_id = image_id
    state._diff_source_ready = True

def letterbox_pil(widget, img: PilImage.Image, slot_index: int = -1) -> PilImage.Image:
    state = widget.runtime_state
    cw, ch = widget.width(), widget.height()
    if cw <= 0 or ch <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
        return img.convert("RGBA")

    img = img.convert("RGBA")
    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:
        state._letterbox_params[slot_index] = (
            (cw - nw) / (2.0 * cw),
            (ch - nh) / (2.0 * ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = (offset_x, offset_y, nw, nh)
            state._clip_overlays_to_content_rect = False
    scaled = img.resize((nw, nh), PilImage.Resampling.BILINEAR)
    result = PilImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
    result.paste(scaled, (offset_x, offset_y))
    return result

def update_letterbox_geometry(widget, img: PilImage.Image | None, slot_index: int = -1):
    state = widget.runtime_state
    cw, ch = widget.width(), widget.height()
    if img is None or cw <= 0 or ch <= 0 or img.width <= 0 or img.height <= 0:
        if slot_index >= 0:
            state._letterbox_params[slot_index] = (0.0, 0.0, 1.0, 1.0)
            if slot_index == 0:
                state._content_rect_px = (0, 0, max(1, cw), max(1, ch))
                state._clip_overlays_to_content_rect = False
        return

    ratio = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
    offset_x = (cw - nw) // 2
    offset_y = (ch - nh) // 2
    if slot_index >= 0:
        state._letterbox_params[slot_index] = (
            (cw - nw) / (2.0 * cw),
            (ch - nh) / (2.0 * ch),
            nw / float(cw),
            nh / float(ch),
        )
        if slot_index == 0:
            state._content_rect_px = (offset_x, offset_y, nw, nh)
            state._clip_overlays_to_content_rect = False

def upload_pil_images(
    widget,
    pil_image1,
    pil_image2,
    source_image1=None,
    source_image2=None,
    source_key=None,
    shader_letterbox: bool = False,
):
    state = widget.runtime_state
    state._stored_pil_images = [pil_image1, pil_image2]
    state._shader_letterbox_mode = bool(shader_letterbox)
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
        source_changed = source_ids != state._source_image_ids
        state._source_pil_images = [source_image1, source_image2]
        state._source_image_ids = source_ids
        if source_changed:
            state._source_images_ready = False
    else:
        source_changed = state._source_image_ids is not None
        state._source_pil_images = [None, None]
        state._source_image_ids = None
        state._source_images_ready = False
    if pil_image1:
        if state._shader_letterbox_mode:
            update_letterbox_geometry(widget, pil_image1, slot_index=0)
            _upload_pil_to_texture_id(widget, pil_image1, widget.texture_ids[0], slot_index=0)
        else:
            lb1 = letterbox_pil(widget, pil_image1, slot_index=0)
            _upload_pil_to_texture_id(widget, lb1, widget.texture_ids[0], slot_index=0)
    if pil_image2:
        if state._shader_letterbox_mode:
            update_letterbox_geometry(widget, pil_image2, slot_index=1)
            _upload_pil_to_texture_id(widget, pil_image2, widget.texture_ids[1], slot_index=1)
        else:
            lb2 = letterbox_pil(widget, pil_image2, slot_index=1)
            _upload_pil_to_texture_id(widget, lb2, widget.texture_ids[1], slot_index=1)
    if has_explicit_source:
        try:
            if source_changed or not state._source_images_ready:
                if source_image1 is not None:
                    upload_source_pil_image(widget, source_image1, 0)
                if source_image2 is not None:
                    upload_source_pil_image(widget, source_image2, 1)
                state._source_images_ready = True
        except Exception:
            state._source_images_ready = False
            if hasattr(widget, "_schedule_source_preload"):
                widget._schedule_source_preload()
    widget.update()

def configure_offscreen_render(
    widget,
    *,
    stored_images,
    source_images,
    content_rect: tuple[int, int, int, int],
    shader_letterbox: bool = False,
):
    state = widget.runtime_state
    prev_stored_images = tuple(state._stored_pil_images)
    prev_source_images = tuple(state._source_pil_images)
    prev_content_rect = state._content_rect_px
    prev_shader_letterbox = state._shader_letterbox_mode
    images_unchanged = (
        prev_stored_images[0] is stored_images[0]
        and prev_stored_images[1] is stored_images[1]
        and prev_source_images[0] is source_images[0]
        and prev_source_images[1] is source_images[1]
    )
    state._store = None
    state._shader_letterbox_mode = bool(shader_letterbox)
    state._letterbox_params[0] = (0.0, 0.0, 1.0, 1.0)
    state._letterbox_params[1] = (0.0, 0.0, 1.0, 1.0)
    state._content_rect_px = content_rect
    state._clip_overlays_to_content_rect = False
    state._stored_pil_images = [stored_images[0], stored_images[1]]
    state._source_pil_images = [source_images[0], source_images[1]]
    state._source_images_ready = bool(source_images[0] is not None and source_images[1] is not None)

    if (
        images_unchanged
        and prev_content_rect == content_rect
        and prev_shader_letterbox == bool(shader_letterbox)
    ):
        return

    _upload_pil_to_texture_id(widget, stored_images[0], widget.texture_ids[0], slot_index=0)
    _upload_pil_to_texture_id(widget, stored_images[1], widget.texture_ids[1], slot_index=1)

    if source_images[0] is not None:
        _upload_pil_to_texture_id(widget, source_images[0], widget._source_texture_ids[0])
    if source_images[1] is not None:
        _upload_pil_to_texture_id(widget, source_images[1], widget._source_texture_ids[1])

def set_background(widget, pixmap: QPixmap | None):
    widget.runtime_state._background_pixmap = pixmap
    if pixmap:
        upload_image(widget, pixmap.toImage(), 0)
    widget.update()

def set_magnifier_content(widget, pixmap: QPixmap | None, top_left: QPoint | None):
    state = widget.runtime_state
    state._magnifier_pixmap = pixmap
    state._magnifier_top_left = top_left

    if pixmap is None or pixmap.isNull() or top_left is None or not widget._mag_tex_ids[0]:
        state._mag_quads[0] = None
        state._mag_quads[1] = None
        state._mag_quads[2] = None
        state._mag_combined_params[0] = None
        state._mag_combined_params[1] = None
        state._mag_combined_params[2] = None
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

    state._mag_quads[1] = None
    state._mag_quads[2] = None
    state._mag_combined_params[0] = None
    state._mag_combined_params[1] = None
    state._mag_combined_params[2] = None
    widget._request_update()

def get_letterbox_params(widget, slot: int = 0) -> tuple:
    state = widget.runtime_state
    if slot < len(state._letterbox_params) and state._letterbox_params[slot]:
        return state._letterbox_params[slot]
    img = state._stored_pil_images[slot] if slot < len(state._stored_pil_images) else None
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
    state = widget.runtime_state
    state._mag_gpu_active = True
    state._mag_gpu_channel_mode = channel_mode
    state._mag_gpu_diff_mode = diff_mode
    state._mag_gpu_diff_threshold = diff_threshold
    state._mag_gpu_interp_mode = interp_mode

    w, h = widget.width(), widget.height()
    for i in range(3):
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

    state._magnifier_radius = slots[0]["radius"] if slots and slots[0] else 0
    if border_color is not None:
        state._magnifier_border_color = border_color
    state._magnifier_border_width = border_width
    widget._request_update()

def set_texture_filter(widget, texture_id: int, gl_filter: int):
    if not texture_id:
        return
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl_filter)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl_filter)

def clear_magnifier_gpu(widget):
    state = widget.runtime_state
    state._mag_gpu_active = False
    for i in range(3):
        state._mag_gpu_slots[i] = None
        state._mag_quads[i] = None
        state._mag_combined_params[i] = None
        state._mag_use_circle_mask[i] = False
    state._mag_quad_ndc = None
    state._magnifier_pixmap = None
    state._magnifier_top_left = None
    state._capture_center = None
    state._capture_radius = 0
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
    if index < 0 or index > 2:
        return
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
    if index < 0 or index > 2:
        return
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
        divider = getattr(viewport.render_config, "magnifier_divider_color", None)
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

def set_layers(widget, background: QPixmap | None, magnifier: QPixmap | None, mag_pos: QPoint | None, coords_snapshot=None):
    if background is not None:
        set_background(widget, background)
    else:
        widget.runtime_state._background_pixmap = None
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
    state = widget.runtime_state
    if pixmap:
        qimage = pixmap.toImage()
        state._store = None
        upload_image(widget, qimage, 0)
        upload_image(widget, qimage, 1)
        state._background_pixmap = pixmap
        state._stored_pil_images = [None, None]
        state._source_pil_images = [None, None]
        state._source_image_ids = [0, 0]
        state._source_images_ready = False
        clear_magnifier_gpu(widget)
        state._capture_center = None
        state._capture_radius = 0
        state._magnifier_centers = []
        state._magnifier_radius = 0
        state._show_divider = False
        state._content_rect_px = (0, 0, max(1, pixmap.width()), max(1, pixmap.height()))
        state._clip_overlays_to_content_rect = False
    else:
        set_layers(widget, None, None, None, None)

def clear(widget):
    state = widget.runtime_state
    state._background_pixmap = None
    state._magnifier_pixmap = None
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
    if widget._diff_source_texture_id:
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget._diff_source_texture_id)
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
    state._diff_source_pil_image = None
    state._diff_source_image_id = 0
    state._diff_source_ready = False
    widget.update()
