import logging
import math

from OpenGL import GL as gl
from PIL import Image
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPalette

from shared.image_processing.pipeline import RenderingPipeline

logger = logging.getLogger("ImproveImgSLI")
_pipeline_cache: dict[str, RenderingPipeline] = {}
_last_diff_interp_log = None

def widget_px_to_screen_px(widget, px_x, px_y):
    w, h = widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return px_x, px_y
    zoom = widget.zoom_level
    pan_x = widget.pan_offset_x
    pan_y = widget.pan_offset_y

    sx = ((px_x / w) - 0.5 + pan_x) * zoom + 0.5
    sy = ((px_y / h) - 0.5 + pan_y) * zoom + 0.5
    return sx * w, sy * h

def get_rendering_pipeline(font_path: str | None) -> RenderingPipeline:
    key = font_path or ""
    pipeline = _pipeline_cache.get(key)
    if pipeline is None:
        pipeline = RenderingPipeline(font_path)
        _pipeline_cache[key] = pipeline
    return pipeline

def clear_with_widget_background(widget):
    palette = widget.palette()
    bg = palette.color(QPalette.ColorRole.Window)
    if not bg.isValid():
        bg = palette.color(QPalette.ColorRole.Base)
    if not bg.isValid():
        bg = QColor(245, 245, 245)
    gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

def clear_with_solid_color(color: QColor):
    gl.glClearColor(color.redF(), color.greenF(), color.blueF(), color.alphaF())
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

def get_zoom_texture_filter(widget) -> int:
    scene = widget.runtime_state._render_scene
    method = str(getattr(scene, "zoom_interpolation_method", "BILINEAR") or "BILINEAR").upper()
    return gl.GL_NEAREST if method == "NEAREST" else gl.GL_LINEAR

def should_render_blank_white(widget) -> bool:
    scene = widget.runtime_state._render_scene
    return bool(getattr(scene, "blank_white", False))

def make_overlay_font(widget, pixel_size: int, bold: bool = False) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(max(1, pixel_size))
    font.setBold(bold)
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font

def draw_raster_shape(
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

def draw_qimage_overlay_texture(widget, overlay: QImage):
    if overlay.isNull() or not widget._ui_overlay_tex_id:
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

def new_overlay_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image

def draw_supersampled_line(
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

    image = new_overlay_image(bbox_w * scale, bbox_h * scale)
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
