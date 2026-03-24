import logging
import math

from OpenGL import GL as gl
from PIL import Image
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPalette
from domain.qt_adapters import color_to_qcolor
from shared.image_processing.pipeline import (
    RenderingPipeline,
)
from shared.image_processing.qt_conversion import pil_to_qimage_zero_copy
from shared_toolkit.ui.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")
_pipeline_cache: dict[str, RenderingPipeline] = {}

def _widget_px_to_screen_px(widget, px_x, px_y):
    w, h = widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return px_x, px_y
    zoom = widget.zoom_level
    pan_x = widget.pan_offset_x
    pan_y = widget.pan_offset_y

    sx = ((px_x / w) - 0.5 + pan_x) * zoom + 0.5
    sy = ((px_y / h) - 0.5 + pan_y) * zoom + 0.5
    return sx * w, sy * h

def _get_rendering_pipeline(font_path: str | None) -> RenderingPipeline:
    key = font_path or ""
    pipeline = _pipeline_cache.get(key)
    if pipeline is None:
        pipeline = RenderingPipeline(font_path)
        _pipeline_cache[key] = pipeline
    return pipeline

def _clear_with_widget_background(widget):
    palette = widget.palette()
    bg = palette.color(QPalette.ColorRole.Window)
    if not bg.isValid():
        bg = palette.color(QPalette.ColorRole.Base)
    if not bg.isValid():
        bg = QColor(245, 245, 245)
    gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

def _clear_with_solid_color(color: QColor):
    gl.glClearColor(color.redF(), color.greenF(), color.blueF(), color.alphaF())
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

def _get_divider_clip_uv(widget) -> tuple[float, float, float, float]:
    store = getattr(widget, "_store", None)
    vp = getattr(store, "viewport", None)
    clip_rect = getattr(vp, "divider_clip_rect", None)
    img = widget._stored_pil_images[0] if getattr(widget, "_stored_pil_images", None) else None
    if clip_rect and img is not None and getattr(img, "width", 0) > 0 and getattr(img, "height", 0) > 0:
        x, y, w, h = clip_rect
        result = (
            x / float(img.width),
            y / float(img.height),
            (x + w) / float(img.width),
            (y + h) / float(img.height),
        )
        return result
    if hasattr(widget, "get_letterbox_params"):
        lb = widget.get_letterbox_params(0)
        result = (lb[0], lb[1], lb[0] + lb[2], lb[1] + lb[3])
        return result
    return (0.0, 0.0, 1.0, 1.0)

def _get_divider_clip_rect_px(widget) -> tuple[int, int, int, int] | None:
    content_rect = getattr(widget, "_content_rect_px", None)
    if not content_rect:
        return None

    x, y, w, h = content_rect
    store = getattr(widget, "_store", None)
    vp = getattr(store, "viewport", None)
    clip_rect = getattr(vp, "divider_clip_rect", None)
    img = widget._stored_pil_images[0] if getattr(widget, "_stored_pil_images", None) else None

    if clip_rect and img is not None and getattr(img, "width", 0) > 0 and getattr(img, "height", 0) > 0:
        clip_x, clip_y, clip_w, clip_h = clip_rect
        x = x + int(round((clip_x / float(img.width)) * w))
        y = y + int(round((clip_y / float(img.height)) * h))
        w = int(round((clip_w / float(img.width)) * w))
        h = int(round((clip_h / float(img.height)) * h))

    x0, y0 = _widget_px_to_screen_px(widget, x, y)
    x1, y1 = _widget_px_to_screen_px(widget, x + w, y + h)
    left = int(round(min(x0, x1)))
    top = int(round(min(y0, y1)))
    width = max(0, int(round(abs(x1 - x0))))
    height = max(0, int(round(abs(y1 - y0))))
    result = (left, top, width, height)
    return result

def _get_content_rect_screen_px(widget) -> tuple[int, int, int, int] | None:
    content_rect = getattr(widget, "_content_rect_px", None)
    if not content_rect:
        return None

    x, y, w, h = content_rect
    if w <= 0 or h <= 0:
        return None

    x0, y0 = _widget_px_to_screen_px(widget, x, y)
    x1, y1 = _widget_px_to_screen_px(widget, x + w, y + h)
    left = int(round(min(x0, x1)))
    top = int(round(min(y0, y1)))
    width = max(0, int(round(abs(x1 - x0))))
    height = max(0, int(round(abs(y1 - y0))))
    if width <= 0 or height <= 0:
        return None
    return (left, top, width, height)

def _get_local_visible_image_rect(
    widget,
    *,
    img_x: int,
    img_y: int,
    img_w: int,
    img_h: int,
) -> QRect | None:
    visible_left = max(0, img_x)
    visible_top = max(0, img_y)
    visible_right = min(widget.width(), img_x + img_w)
    visible_bottom = min(widget.height(), img_y + img_h)
    if visible_right <= visible_left or visible_bottom <= visible_top:
        return None
    return QRect(
        int(visible_left - img_x),
        int(visible_top - img_y),
        int(visible_right - visible_left),
        int(visible_bottom - visible_top),
    )

def _get_zoom_texture_filter(widget) -> int:
    store = getattr(widget, "_store", None)
    render_cfg = getattr(getattr(store, "viewport", None), "render_config", None)
    method = str(getattr(render_cfg, "zoom_interpolation_method", "BILINEAR") or "BILINEAR").upper()
    return gl.GL_NEAREST if method == "NEAREST" else gl.GL_LINEAR

def _should_render_blank_white(widget) -> bool:
    store = getattr(widget, "_store", None)
    if store is None:
        return False

    doc = getattr(store, "document", None)
    if doc is None:
        return False

    return not bool(doc.image1_path and doc.image2_path)

def _make_overlay_font(widget, pixel_size: int, bold: bool = False) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(max(1, pixel_size))
    font.setBold(bold)
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font

def _draw_raster_shape(
    painter: QPainter,
    rect: QRectF,
    fill_color: QColor,
    border_color: QColor,
    border_width: float,
    radius: float,
    ellipse: bool = False,
):
    aligned = rect.toAlignedRect()
    if aligned.width() <= 0 or aligned.height() <= 0:
        return

    scale = 4
    image = QImage(
        aligned.width() * scale,
        aligned.height() * scale,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)

    image_painter = QPainter(image)
    try:
        image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        image_painter.setBrush(fill_color)
        pen = QPen(border_color, border_width * scale)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        image_painter.setPen(pen)

        local_rect = QRectF(
            (border_width * scale) / 2.0,
            (border_width * scale) / 2.0,
            max(1.0, image.width() - border_width * scale),
            max(1.0, image.height() - border_width * scale),
        )
        if ellipse:
            image_painter.drawEllipse(local_rect)
        else:
            path = QPainterPath()
            path.addRoundedRect(local_rect, radius * scale, radius * scale)
            image_painter.drawPath(path)
    finally:
        image_painter.end()

    smoothed = image.scaled(
        aligned.size(),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawImage(aligned.topLeft(), smoothed)

def _draw_qimage_overlay_texture(widget, overlay: QImage):
    if overlay.isNull() or not getattr(widget, "_ui_overlay_tex_id", 0):
        return

    qimg = overlay.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())

    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._ui_overlay_tex_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        qimg.width(),
        qimg.height(),
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        bytes(ptr),
    )

    widget.shader_program.bind()
    widget.vao.bind()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._ui_overlay_tex_id)
    widget.shader_program.setUniformValue("image1", 0)
    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._ui_overlay_tex_id)
    widget.shader_program.setUniformValue("image2", 1)
    widget.shader_program.setUniformValue("splitPosition", 1.0)
    widget.shader_program.setUniformValue("isHorizontal", False)
    widget.shader_program.setUniformValue("zoom", 1.0)
    widget.shader_program.setUniformValue("offset", 0.0, 0.0)
    widget.shader_program.setUniformValue("showDivider", False)
    widget.shader_program.setUniformValue("dividerColor", 0.0, 0.0, 0.0, 0.0)
    widget.shader_program.setUniformValue("dividerThickness", 0.0)
    widget.shader_program.setUniformValue("dividerClip", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("channelMode", 0)
    widget.shader_program.setUniformValue("useSourceTex", False)
    widget.shader_program.setUniformValue("letterbox1", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox2", 0.0, 0.0, 1.0, 1.0)
    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

def _new_overlay_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image

def _draw_supersampled_line(
    painter: QPainter,
    p1: QPointF,
    p2: QPointF,
    color: QColor,
    thickness: float,
):
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        return

    scale = 4
    padding = max(4.0, thickness + 2.0)
    left = int(math.floor(min(p1.x(), p2.x()) - padding))
    top = int(math.floor(min(p1.y(), p2.y()) - padding))
    right = int(math.ceil(max(p1.x(), p2.x()) + padding))
    bottom = int(math.ceil(max(p1.y(), p2.y()) + padding))
    bbox_w = right - left
    bbox_h = bottom - top
    if bbox_w <= 0 or bbox_h <= 0:
        return

    image = _new_overlay_image(bbox_w * scale, bbox_h * scale)
    image_painter = QPainter(image)
    try:
        image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color, max(1.0, thickness * scale))
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        image_painter.setPen(pen)
        image_painter.drawLine(
            QPointF((p1.x() - left) * scale, (p1.y() - top) * scale),
            QPointF((p2.x() - left) * scale, (p2.y() - top) * scale),
        )
    finally:
        image_painter.end()

    smoothed = image.scaled(
        bbox_w,
        bbox_h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawImage(QPointF(float(left), float(top)), smoothed)

def _build_filename_overlay_image(widget) -> QImage | None:
    store = getattr(widget, "_store", None)
    if store is None or not getattr(store.viewport, "include_file_names_in_saved", False):
        return None
    if not getattr(store, "document", None):
        return None

    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None
    if not math.isclose(float(getattr(widget, "zoom_level", 1.0)), 1.0, rel_tol=0.0, abs_tol=1e-6):
        return None

    content_rect = _get_content_rect_screen_px(widget)
    if content_rect:
        img_x, img_y, img_w, img_h = content_rect
    else:
        display_rect = getattr(store.viewport, "image_display_rect_on_label", None)
        if display_rect:
            img_x = int(getattr(display_rect, "x", 0))
            img_y = int(getattr(display_rect, "y", 0))
            img_w = int(getattr(display_rect, "w", 0))
            img_h = int(getattr(display_rect, "h", 0))
        else:
            img_x, img_y, img_w, img_h = 0, 0, width, height
    if img_w <= 0 or img_h <= 0:
        return None

    name1 = store.document.get_current_display_name(1) or ""
    name2 = store.document.get_current_display_name(2) or ""
    if not name1 and not name2:
        return None

    local_content_rect = getattr(widget, "_content_rect_px", None)
    logical_img_w = local_content_rect[2] if local_content_rect else img_w
    logical_img_h = local_content_rect[3] if local_content_rect else img_h
    text_placement_mode = str(getattr(store.viewport, "text_placement_mode", "edges"))
    split_value = float(getattr(store.viewport, "split_position_visual", 0.5))
    is_horizontal = bool(getattr(store.viewport, "is_horizontal", False))
    divider_thickness = int(getattr(store.viewport, "divider_line_thickness", 0))
    half_line = (divider_thickness + 1) // 2
    safe_gap = 5

    if is_horizontal:
        logical_split_px = int(round(logical_img_h * split_value))
        text_layout_key = (
            logical_split_px if text_placement_mode == "split_line" else None,
            max(0, logical_img_w - (safe_gap * 2)),
        )
    else:
        logical_split_px = int(round(logical_img_w * split_value))
        text_layout_key = (
            max(0, logical_split_px - half_line - safe_gap),
            max(0, (logical_img_w - 1) - logical_split_px - half_line - safe_gap),
        )

    cache_key = (
        width,
        height,
        img_x,
        img_y,
        img_w,
        img_h,
        bool(getattr(store.viewport, "is_interactive_mode", False)),
        is_horizontal,
        text_layout_key,
        bool(getattr(store.viewport, "draw_text_background", True)),
        text_placement_mode,
        int(getattr(store.viewport, "font_size_percent", 100)),
        int(getattr(store.viewport, "font_weight", 0)),
        int(getattr(store.viewport, "text_alpha_percent", 100)),
        getattr(store.viewport, "file_name_color", None),
        getattr(store.viewport, "file_name_bg_color", None),
        name1,
        name2,
    )
    if (
        getattr(widget, "_filename_overlay_cache_key", None) == cache_key
        and getattr(widget, "_filename_overlay_cached_image", None) is not None
    ):
        return widget._filename_overlay_cached_image

    local_visible_rect = _get_local_visible_image_rect(
        widget,
        img_x=img_x,
        img_y=img_y,
        img_w=img_w,
        img_h=img_h,
    )
    if local_visible_rect is None:
        return None

    font_path = FontManager.get_instance().get_font_path_for_image_text(store)
    pipeline = _get_rendering_pipeline(font_path)
    patch = Image.new("RGBA", (max(1, img_w), max(1, img_h)), (0, 0, 0, 0))
    split_local = int(round((img_h if is_horizontal else img_w) * split_value))
    pipeline.text_drawer.draw_filenames_on_image(
        store,
        patch,
        QRect(0, 0, int(img_w), int(img_h)),
        split_local,
        divider_thickness,
        name1,
        name2,
        visible_rect=local_visible_rect,
    )
    if patch is None:
        return None
    patch_image = pil_to_qimage_zero_copy(patch)
    if patch_image is None or patch_image.isNull():
        return None

    overlay = _new_overlay_image(width, height)
    painter = QPainter(overlay)
    try:
        painter.drawImage(
            QPointF(float(img_x), float(img_y)),
            patch_image,
        )
    finally:
        painter.end()
    widget._filename_overlay_cache_key = cache_key
    widget._filename_overlay_cached_image = overlay
    return overlay

def _build_drag_overlay_image(widget) -> QImage | None:
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None

    cache_key = (
        width,
        height,
        bool(getattr(widget, "_drag_overlay_horizontal", False)),
        tuple(getattr(widget, "_drag_overlay_texts", ("", ""))),
    )
    if (
        getattr(widget, "_drag_overlay_cache_key", None) == cache_key
        and getattr(widget, "_drag_overlay_cached_image", None) is not None
    ):
        return widget._drag_overlay_cached_image

    margin = 10.0
    half_margin = margin / 2.0
    if getattr(widget, "_drag_overlay_horizontal", False):
        half_height = height / 2.0
        rect1 = QRectF(
            margin,
            margin,
            max(1.0, width - 2.0 * margin),
            max(1.0, half_height - margin - half_margin),
        )
        rect2 = QRectF(
            margin,
            half_height + half_margin,
            max(1.0, width - 2.0 * margin),
            max(1.0, half_height - margin - half_margin),
        )
    else:
        half_width = width / 2.0
        rect1 = QRectF(
            margin,
            margin,
            max(1.0, half_width - margin - half_margin),
            max(1.0, height - 2.0 * margin),
        )
        rect2 = QRectF(
            half_width + half_margin,
            margin,
            max(1.0, half_width - margin - half_margin),
            max(1.0, height - 2.0 * margin),
        )

    image = _new_overlay_image(width, height)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(_make_overlay_font(widget, 20))

        for rect, text in zip((rect1, rect2), widget._drag_overlay_texts):
            _draw_raster_shape(
                painter,
                rect,
                QColor(0, 100, 200, 153),
                QColor(255, 255, 255, 179),
                1.25,
                10.0,
            )
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                rect.adjusted(15.0, 15.0, -15.0, -15.0),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text,
            )
    finally:
        painter.end()
    widget._drag_overlay_cache_key = cache_key
    widget._drag_overlay_cached_image = image
    return image

def _paint_drag_overlay_pass(widget):
    if not getattr(widget, "_drag_overlay_visible", False):
        return
    overlay = _build_drag_overlay_image(widget)
    if overlay is not None:
        _draw_qimage_overlay_texture(widget, overlay)

def _paint_filename_overlay_pass(widget):
    overlay = _build_filename_overlay_image(widget)
    if overlay is not None:
        _draw_qimage_overlay_texture(widget, overlay)

def _build_paste_overlay_image(widget) -> QImage | None:
    widget._update_paste_overlay_rects()
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None

    image = _new_overlay_image(width, height)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(widget.rect(), QColor(0, 0, 0, 0))

        buttons = []
        if not widget._paste_overlay_rects["up"].isNull():
            buttons.append(("up", widget._paste_overlay_rects["up"], widget._paste_overlay_texts["up"]))
        if not widget._paste_overlay_rects["down"].isNull():
            buttons.append(("down", widget._paste_overlay_rects["down"], widget._paste_overlay_texts["down"]))
        if not widget._paste_overlay_rects["left"].isNull():
            buttons.append(("left", widget._paste_overlay_rects["left"], widget._paste_overlay_texts["left"]))
        if not widget._paste_overlay_rects["right"].isNull():
            buttons.append(("right", widget._paste_overlay_rects["right"], widget._paste_overlay_texts["right"]))

        for direction, rect, text in buttons:
            is_hovered = widget._paste_overlay_hovered_button == direction
            if is_hovered:
                bg_color = QColor(255, 255, 255, 230)
                text_color = QColor(0, 0, 0)
                border_color = QColor(100, 150, 255)
                border_width = 3.0
            else:
                bg_color = QColor(255, 255, 255, 200)
                text_color = QColor(50, 50, 50)
                border_color = QColor(200, 200, 200)
                border_width = 2.0

            _draw_raster_shape(
                painter,
                rect,
                bg_color,
                border_color,
                border_width,
                10.0,
            )

            painter.setFont(
                _make_overlay_font(widget, 14 if is_hovered else 12, bold=is_hovered)
            )
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        cancel_rect = widget._paste_overlay_rects["cancel"]
        if not cancel_rect.isNull():
            is_hovered = widget._paste_overlay_hovered_button == "cancel"
            cancel_bg = QColor(220, 220, 220, 200) if is_hovered else QColor(180, 180, 180, 150)
            _draw_raster_shape(
                painter,
                cancel_rect,
                cancel_bg,
                QColor(100, 100, 100),
                2.0,
                0.0,
                ellipse=True,
            )

            center = cancel_rect.center()
            offset = 15.0
            line_pen = QPen(QColor(80, 80, 80), 2.0)
            line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(line_pen)
            painter.drawLine(
                QPointF(center.x() - offset, center.y() - offset),
                QPointF(center.x() + offset, center.y() + offset),
            )
            painter.drawLine(
                QPointF(center.x() - offset, center.y() + offset),
                QPointF(center.x() + offset, center.y() - offset),
            )
    finally:
        painter.end()
    return image

def _paint_paste_overlay_pass(widget):
    if not getattr(widget, "_paste_overlay_visible", False):
        return
    overlay = _build_paste_overlay_image(widget)
    if overlay is not None:
        _draw_qimage_overlay_texture(widget, overlay)

def _compute_render_config(widget):
    if widget._store:
        from domain.qt_adapters import color_to_qcolor

        vp = widget._store.viewport
        single_image_preview = getattr(vp, "showing_single_image_mode", 0) != 0
        widget.is_horizontal = vp.is_horizontal
        w, h = widget.width(), widget.height()
        img1 = widget._stored_pil_images[0]
        if img1 and w > 0 and h > 0:
            ratio = min(w / img1.width, h / img1.height)
            nw = max(1, int(img1.width * ratio))
            nh = max(1, int(img1.height * ratio))
            img_x = (w - nw) // 2
            img_y = (h - nh) // 2

            if vp.is_horizontal:
                base = (img_y + nh * vp.split_position_visual) / h
                pan = widget.pan_offset_y
            else:
                base = (img_x + nw * vp.split_position_visual) / w
                pan = widget.pan_offset_x

            widget.split_position = (base - 0.5 + pan) * widget.zoom_level + 0.5
        else:
            widget.split_position = vp.split_position_visual
        return {
            "show_div": (
                vp.divider_line_visible
                and getattr(vp, "diff_mode", "off") == "off"
                and not single_image_preview
            ),
            "div_color": color_to_qcolor(vp.divider_line_color),
            "div_thickness": vp.divider_line_thickness,
            "render_magnifiers": vp.use_magnifier,
            "border_color": color_to_qcolor(vp.magnifier_border_color),
            "capture_color": color_to_qcolor(vp.capture_ring_color),
            "channel_mode_int": {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
                getattr(vp, "channel_view_mode", "RGB"), 0
            ) if widget._apply_channel_mode_in_shader else 0,
        }

    return {
        "show_div": widget._show_divider,
        "div_color": widget._divider_color,
        "div_thickness": widget._divider_thickness,
        "render_magnifiers": True,
        "border_color": widget._magnifier_border_color,
        "capture_color": widget._capture_color,
        "channel_mode_int": 0,
    }

def _begin_content_scissor(widget):
    if not getattr(widget, "_clip_overlays_to_content_rect", False):
        return False
    rect = getattr(widget, "_content_rect_px", None)
    if not rect:
        return False

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return False

    viewport_h = widget.height()
    gl.glEnable(gl.GL_SCISSOR_TEST)
    gl.glScissor(int(x), int(max(0, viewport_h - (y + h))), int(w), int(h))
    return True

def _end_content_scissor(enabled):
    if enabled:
        gl.glDisable(gl.GL_SCISSOR_TEST)

def _paint_capture_ring_pass(widget, capture_color):
    w, h = widget.width(), widget.height()
    if not (widget._circle_shader and w > 0 and h > 0 and widget._capture_center and widget._capture_radius > 0):
        return

    scissor_enabled = _begin_content_scissor(widget)
    pid = widget._circle_shader.programId()
    widget._circle_shader.bind()
    widget.vao.bind()

    cx, cy = _widget_px_to_screen_px(widget, widget._capture_center.x(), widget._capture_center.y())
    scaled_radius = widget._capture_radius * widget.zoom_level
    line_width_px = max(2.0, float(scaled_radius * 2.0) * 0.0105)

    gl.glUniform2f(gl.glGetUniformLocation(pid, "resolution"), float(w), float(h))
    gl.glUniform2f(
        gl.glGetUniformLocation(pid, "center_px"),
        float(cx),
        float(cy),
    )
    gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), float(scaled_radius))
    gl.glUniform1f(gl.glGetUniformLocation(pid, "lineWidth_px"), float(line_width_px))
    gl.glUniform4f(
        gl.glGetUniformLocation(pid, "color"),
        capture_color.redF(),
        capture_color.greenF(),
        capture_color.blueF(),
        capture_color.alphaF(),
    )
    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)

    widget.vao.release()
    widget._circle_shader.release()
    _end_content_scissor(scissor_enabled)

def _paint_guides_pass(widget):
    if not (
        widget._show_guides
        and widget._guides_thickness > 0
        and widget._capture_center is not None
        and widget._capture_radius > 0
        and widget._magnifier_centers
        and widget._magnifier_radius > 0
    ):
        return

    def _draw_line(painter, p1, p2, r1, r2, color, interactive, thickness):
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist <= (r1 + r2) or dist <= 1e-6:
            return

        nx, ny = dx / dist, dy / dist
        ax, ay = p1.x() + nx * r1, p1.y() + ny * r1
        bx, by = p2.x() - nx * r2, p2.y() - ny * r2

        if interactive:
            pen = QPen(color, float(thickness))
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
            return

        _draw_supersampled_line(
            painter,
            QPointF(ax, ay),
            QPointF(bx, by),
            color,
            float(thickness),
        )

    vp = widget._store.viewport if widget._store is not None else None
    is_interactive = bool(getattr(vp, "is_interactive_mode", False))
    optimize_smoothing = bool(getattr(vp, "optimize_laser_smoothing", False))
    if is_interactive:
        if optimize_smoothing:
            interactive_line = False
        else:
            interactive_line = True
    else:
        interactive_line = False

    w = widget.width()
    h = widget.height()
    overlay = _new_overlay_image(w, h)
    painter = QPainter(overlay)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(
        widget._laser_color.red(),
        widget._laser_color.green(),
        widget._laser_color.blue(),
        255,
    )
    zoom = widget.zoom_level
    cc_x, cc_y = _widget_px_to_screen_px(widget, widget._capture_center.x(), widget._capture_center.y())
    cap_center = QPointF(cc_x, cc_y)
    cap_radius = float(widget._capture_radius) * zoom
    mag_radius = float(widget._magnifier_radius) * zoom
    thickness = max(1, int(widget._guides_thickness))
    try:
        for mag_center in widget._magnifier_centers:
            if mag_center is None:
                continue
            mc_x, mc_y = _widget_px_to_screen_px(widget, mag_center.x(), mag_center.y())
            _draw_line(
                painter,
                QPointF(mc_x, mc_y),
                cap_center,
                mag_radius,
                cap_radius,
                color,
                interactive_line,
                thickness,
            )
    finally:
        painter.end()

    if not getattr(widget, "_guides_tex_id", 0):
        return

    qimg = overlay.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(
        gl.GL_TEXTURE_2D,
        0,
        gl.GL_RGBA,
        qimg.width(),
        qimg.height(),
        0,
        gl.GL_RGBA,
        gl.GL_UNSIGNED_BYTE,
        bytes(ptr),
    )

    widget.shader_program.bind()
    widget.vao.bind()

    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    widget.shader_program.setUniformValue("image1", 0)
    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, widget._guides_tex_id)
    widget.shader_program.setUniformValue("image2", 1)

    widget.shader_program.setUniformValue("splitPosition", 1.0)
    widget.shader_program.setUniformValue("isHorizontal", False)
    widget.shader_program.setUniformValue("zoom", 1.0)
    widget.shader_program.setUniformValue("offset", 0.0, 0.0)
    widget.shader_program.setUniformValue("showDivider", False)
    widget.shader_program.setUniformValue("dividerColor", 0.0, 0.0, 0.0, 0.0)
    widget.shader_program.setUniformValue("dividerThickness", 0.0)
    widget.shader_program.setUniformValue("dividerClip", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("channelMode", 0)
    widget.shader_program.setUniformValue("useSourceTex", False)
    widget.shader_program.setUniformValue("letterbox1", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox2", 0.0, 0.0, 1.0, 1.0)

    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

def _paint_divider_overlay_pass(widget, cfg):
    if not cfg.get("show_div", False):
        return

    clip_rect = _get_divider_clip_rect_px(widget)
    if not clip_rect:
        return

    clip_x, clip_y, clip_w, clip_h = clip_rect
    if clip_w <= 0 or clip_h <= 0:
        return

    w = widget.width()
    h = widget.height()
    if w <= 0 or h <= 0:
        return

    overlay = _new_overlay_image(w, h)
    painter = QPainter(overlay)
    try:
        color = cfg["div_color"]
        thickness = max(1, int(round(cfg["div_thickness"])))
        if widget.is_horizontal:
            y = int(round(widget.split_position * h))
            painter.fillRect(
                clip_x,
                y - thickness // 2,
                clip_w,
                thickness,
                color,
            )
        else:
            x = int(round(widget.split_position * w))
            painter.fillRect(
                x - thickness // 2,
                clip_y,
                thickness,
                clip_h,
                color,
            )
    finally:
        painter.end()

    _draw_qimage_overlay_texture(widget, overlay)

def _paint_magnifier_pass(widget, border_color, render_magnifiers):
    w, h = widget.width(), widget.height()
    if not (widget._mag_shader and w > 0 and h > 0 and render_magnifiers):
        return

    scissor_enabled = _begin_content_scissor(widget)
    pid = widget._mag_shader.programId()
    is_gpu = widget._mag_gpu_active
    use_source_textures = is_gpu and widget._source_images_ready
    bg_filter = gl.GL_LINEAR if widget._mag_gpu_interp_mode == 1 else gl.GL_NEAREST

    zoom = widget.zoom_level
    pan_x = widget.pan_offset_x
    pan_y = widget.pan_offset_y

    for i, quad in enumerate(widget._mag_quads):
        if not quad:
            continue
        x0, y0, x1, y1, _cx_px, _cy_px, r_px = quad

        gpu_slot = widget._mag_gpu_slots[i] if is_gpu and i < len(widget._mag_gpu_slots) else None
        if not gpu_slot:
            tid = widget._mag_tex_ids[i] if i < len(widget._mag_tex_ids) else 0
            if not tid:
                continue

        border_width = max(
            float(getattr(widget, "_magnifier_border_width", 2.0)),
            float(r_px * 2.0) * 0.0105,
        )
        content_radius = max(1.0, r_px - border_width + 1.0)

        widget._mag_shader.bind()
        widget._mag_shader.setUniformValue("quadBounds", x0, y0, x1, y1)
        widget._mag_shader.setUniformValue("magZoom", zoom)
        gl.glUniform2f(gl.glGetUniformLocation(pid, "magPan"), pan_x, pan_y)
        widget._mag_shader.setUniformValue("useCircleMask", True)
        gl.glActiveTexture(gl.GL_TEXTURE4)
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget._circle_mask_tex_id)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "circleMaskTex"), 4)

        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), r_px)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), border_width)
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "borderColor"),
            border_color.redF(),
            border_color.greenF(),
            border_color.blueF(),
            border_color.alphaF(),
        )

        if gpu_slot:
            gl.glUniform1i(gl.glGetUniformLocation(pid, "gpuSampling"), 1)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "channelMode"), widget._mag_gpu_channel_mode)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "diffMode"), widget._mag_gpu_diff_mode)
            gl.glUniform1f(gl.glGetUniformLocation(pid, "diffThreshold"), widget._mag_gpu_diff_threshold)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "interpMode"), widget._mag_gpu_interp_mode)

            uv1 = gpu_slot.get("uv_rect", (0, 0, 1, 1))
            uv2 = gpu_slot.get("uv_rect2", uv1)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect1"), *uv1)
            gl.glUniform4f(gl.glGetUniformLocation(pid, "uvRect2"), *uv2)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "sourceMode"), gpu_slot.get("source", 0))

            is_combined = gpu_slot.get("is_combined", False)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "isCombined"), int(is_combined))
            if is_combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), gpu_slot.get("internal_split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(gpu_slot.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), int(gpu_slot.get("divider_visible", True)))
                dc2 = gpu_slot.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
                gl.glUniform1f(
                    gl.glGetUniformLocation(pid, "combDividerThickness"),
                    gpu_slot.get("divider_thickness_uv", 0.005),
                )
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), 0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), 1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

            tex1 = widget._source_texture_ids[0] if use_source_textures else widget.texture_ids[0]
            tex2 = widget._source_texture_ids[1] if use_source_textures else widget.texture_ids[1]
            gl.glActiveTexture(gl.GL_TEXTURE2)
            widget._set_texture_filter(tex1, bg_filter)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex1"), 2)
            gl.glActiveTexture(gl.GL_TEXTURE3)
            widget._set_texture_filter(tex2, bg_filter)
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "bgTex2"), 3)
            widget._mag_shader.setUniformValue("magTex", 0)
            widget._mag_shader.setUniformValue("magTex2", 1)
        else:
            gl.glUniform1i(gl.glGetUniformLocation(pid, "gpuSampling"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "channelMode"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "diffMode"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "sourceMode"), 0)
            gl.glUniform1i(gl.glGetUniformLocation(pid, "interpMode"), 1)

            comb_params = widget._mag_combined_params[i] if i < len(widget._mag_combined_params) else None
            is_combined = comb_params is not None
            gl.glUniform1i(gl.glGetUniformLocation(pid, "isCombined"), int(is_combined))
            if is_combined:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), comb_params.get("split", 0.5))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), int(comb_params.get("horizontal", False)))
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), int(comb_params.get("divider_visible", True)))
                dc2 = comb_params.get("divider_color", (1.0, 1.0, 1.0, 0.9))
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), *dc2)
                gl.glUniform1f(
                    gl.glGetUniformLocation(pid, "combDividerThickness"),
                    comb_params.get("divider_thickness_uv", 0.005),
                )
            else:
                gl.glUniform1f(gl.glGetUniformLocation(pid, "internalSplit"), 0.5)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "combHorizontal"), 0)
                gl.glUniform1i(gl.glGetUniformLocation(pid, "showCombDivider"), 0)
                gl.glUniform4f(gl.glGetUniformLocation(pid, "combDividerColor"), 1.0, 1.0, 1.0, 0.9)
                gl.glUniform1f(gl.glGetUniformLocation(pid, "combDividerThickness"), 0.0)

            gl.glActiveTexture(gl.GL_TEXTURE0)
            gl.glBindTexture(gl.GL_TEXTURE_2D, widget._mag_tex_ids[i])
            widget._mag_shader.setUniformValue("magTex", 0)
            if is_combined:
                comb_tid = widget._mag_combined_tex_ids[i] if i < len(widget._mag_combined_tex_ids) else 0
                gl.glActiveTexture(gl.GL_TEXTURE2)
                gl.glBindTexture(gl.GL_TEXTURE_2D, comb_tid)
                widget._mag_shader.setUniformValue("magTex2", 2)

        widget.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        widget._mag_shader.release()

        content_x0 = ((_cx_px - content_radius) / w) * 2.0 - 1.0
        content_x1 = ((_cx_px + content_radius) / w) * 2.0 - 1.0
        content_y1 = 1.0 - (((_cy_px - content_radius) / h) * 2.0)
        content_y0 = 1.0 - (((_cy_px + content_radius) / h) * 2.0)

        widget._mag_shader.bind()
        widget._mag_shader.setUniformValue(
            "quadBounds", content_x0, content_y0, content_x1, content_y1
        )
        widget._mag_shader.setUniformValue("magZoom", zoom)
        gl.glUniform2f(gl.glGetUniformLocation(pid, "magPan"), pan_x, pan_y)
        widget._mag_shader.setUniformValue("useCircleMask", True)
        gl.glActiveTexture(gl.GL_TEXTURE4)
        gl.glBindTexture(gl.GL_TEXTURE_2D, widget._circle_mask_tex_id)
        gl.glUniform1i(gl.glGetUniformLocation(pid, "circleMaskTex"), 4)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "radius_px"), content_radius)
        gl.glUniform1f(gl.glGetUniformLocation(pid, "borderWidth"), 0.0)
        gl.glUniform4f(
            gl.glGetUniformLocation(pid, "borderColor"),
            0.0,
            0.0,
            0.0,
            0.0,
        )

        widget.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        widget.vao.release()
        widget._mag_shader.release()

    if is_gpu:
        tex1 = widget._source_texture_ids[0] if use_source_textures else widget.texture_ids[0]
        tex2 = widget._source_texture_ids[1] if use_source_textures else widget.texture_ids[1]
        widget._set_texture_filter(tex1, gl.GL_LINEAR)
        widget._set_texture_filter(tex2, gl.GL_LINEAR)
    _end_content_scissor(scissor_enabled)

def _paint_magnifier_shadow_pass(widget, render_magnifiers):
    return

def paint_gl(widget):
    if not widget.shader_program:
        return

    if _should_render_blank_white(widget):
        _clear_with_widget_background(widget)
        _paint_drag_overlay_pass(widget)
        _paint_paste_overlay_pass(widget)
        return

    _clear_with_widget_background(widget)
    if not any(widget._images_uploaded):
        _paint_drag_overlay_pass(widget)
        _paint_paste_overlay_pass(widget)
        return

    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    widget.shader_program.bind()
    widget.vao.bind()

    use_hires = bool(
        getattr(widget, "_shader_letterbox_mode", False)
        and
        widget.zoom_level > 1.0
        and widget._source_images_ready
        and widget._source_texture_ids[0]
        and widget._source_texture_ids[1]
    )
    tex1 = widget._source_texture_ids[0] if use_hires else widget.texture_ids[0]
    tex2 = widget._source_texture_ids[1] if use_hires else widget.texture_ids[1]
    zoom_filter = _get_zoom_texture_filter(widget)
    widget._set_texture_filter(tex1, zoom_filter)
    widget._set_texture_filter(tex2, zoom_filter)

    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex1)
    widget.shader_program.setUniformValue("image1", 0)

    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex2)
    widget.shader_program.setUniformValue("image2", 1)

    cfg = _compute_render_config(widget)
    widget.shader_program.setUniformValue("splitPosition", widget.split_position)
    widget.shader_program.setUniformValue("isHorizontal", widget.is_horizontal)
    widget.shader_program.setUniformValue("zoom", widget.zoom_level)
    widget.shader_program.setUniformValue("offset", widget.pan_offset_x, widget.pan_offset_y)
    widget.shader_program.setUniformValue("showDivider", False)

    dc = cfg["div_color"]
    dim = widget.height() if widget.is_horizontal else widget.width()
    thickness_ndc = ((cfg["div_thickness"] * 0.5) / dim) if dim > 0 else 0.001
    divider_clip = _get_divider_clip_uv(widget)
    widget.shader_program.setUniformValue("dividerColor", dc.redF(), dc.greenF(), dc.blueF(), dc.alphaF())
    widget.shader_program.setUniformValue("dividerThickness", thickness_ndc)
    widget.shader_program.setUniformValue("dividerClip", *divider_clip)
    widget.shader_program.setUniformValue("channelMode", cfg["channel_mode_int"])
    widget.shader_program.setUniformValue("useSourceTex", use_hires)
    if getattr(widget, "_shader_letterbox_mode", False):
        lb1 = widget.get_letterbox_params(0) if hasattr(widget, "get_letterbox_params") else (0.0, 0.0, 1.0, 1.0)
        lb2 = widget.get_letterbox_params(1) if hasattr(widget, "get_letterbox_params") else (0.0, 0.0, 1.0, 1.0)
    else:
        lb1 = (0.0, 0.0, 1.0, 1.0)
        lb2 = (0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox1", *lb1)
    widget.shader_program.setUniformValue("letterbox2", *lb2)

    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

    _paint_divider_overlay_pass(widget, cfg)
    _paint_guides_pass(widget)
    _paint_capture_ring_pass(widget, cfg["capture_color"])
    _paint_magnifier_shadow_pass(widget, cfg["render_magnifiers"])
    _paint_magnifier_pass(widget, cfg["border_color"], cfg["render_magnifiers"])
    _paint_filename_overlay_pass(widget)
    _paint_drag_overlay_pass(widget)
    _paint_paste_overlay_pass(widget)
