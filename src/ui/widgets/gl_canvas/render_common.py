from OpenGL import GL as gl
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPalette

from ui.canvas_infra.viewport.state import get_pan_offset_x, get_pan_offset_y, get_zoom_level

def widget_px_to_screen_px(widget, px_x, px_y):
    w, h = widget.width(), widget.height()
    if w <= 0 or h <= 0:
        return px_x, px_y
    zoom = get_zoom_level(widget)
    pan_x = get_pan_offset_x(widget)
    pan_y = get_pan_offset_y(widget)

    sx = ((px_x / w) - 0.5 + pan_x) * zoom + 0.5
    sy = ((px_y / h) - 0.5 + pan_y) * zoom + 0.5
    return sx * w, sy * h

def clear_with_widget_background(widget):
    palette = widget.palette()
    bg = palette.color(QPalette.ColorRole.Window)
    if not bg.isValid():
        bg = palette.color(QPalette.ColorRole.Base)
    if not bg.isValid():
        bg = QColor(245, 245, 245)
    gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

def get_zoom_texture_filter(scene_frame) -> int:
    method = str(getattr(scene_frame, "zoom_interpolation_method", "BILINEAR") or "BILINEAR").upper()
    return gl.GL_NEAREST if method == "NEAREST" else gl.GL_LINEAR

def should_render_blank_white(scene_frame) -> bool:
    return bool(getattr(scene_frame, "blank_white", False))

def new_overlay_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image

def upload_qimage_texture(texture_id: int, overlay: QImage) -> bool:
    if overlay.isNull() or not texture_id:
        return False

    qimg = overlay.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.constBits()
    ptr.setsize(qimg.sizeInBytes())

    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
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
    return True

def draw_overlay_texture(widget, texture_id: int):
    if not texture_id:
        return

    widget.shader_program.bind()
    widget.vao.bind()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    widget.shader_program.setUniformValue("image1", 0)
    gl.glActiveTexture(gl.GL_TEXTURE1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    widget.shader_program.setUniformValue("image2", 1)
    widget.shader_program.setUniformValue("splitPosition", 1.0)
    widget.shader_program.setUniformValue("isHorizontal", False)
    widget.shader_program.setUniformValue("zoom", 1.0)
    widget.shader_program.setUniformValue("offset", 0.0, 0.0)
    widget.shader_program.setUniformValue("channelMode", 0)
    widget.shader_program.setUniformValue("useSourceTex", False)
    widget.shader_program.setUniformValue("letterbox1", 0.0, 0.0, 1.0, 1.0)
    widget.shader_program.setUniformValue("letterbox2", 0.0, 0.0, 1.0, 1.0)
    gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
    widget.vao.release()
    widget.shader_program.release()

def draw_qimage_overlay_texture(widget, overlay: QImage):
    texture_id = int(getattr(widget, "_ui_overlay_tex_id", 0) or 0)
    if upload_qimage_texture(texture_id, overlay):
        draw_overlay_texture(widget, texture_id)
