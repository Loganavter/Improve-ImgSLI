from OpenGL import GL as gl
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QImage, QPixmap

from .base_images import (
    clear_diff_texture,
    upload_image,
    upload_pil_images,
)
from .magnifier import clear_magnifier_gpu, set_magnifier_content

def set_background(widget, pixmap: QPixmap | None):
    widget.runtime_state._background_pixmap = pixmap
    if pixmap:
        upload_image(widget, pixmap.toImage(), 0)
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
    display_cache_key=None,
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
            display_cache_key,
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
        state._stored_image_ids = None
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
    clear_diff_texture(widget)
    widget.update()
