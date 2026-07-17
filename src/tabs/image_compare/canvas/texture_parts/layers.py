from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QPixmap

from tabs.image_compare.canvas.feature_overlay_gpu import (
    clear_feature_overlay_gpu,
    set_feature_overlay_content,
)

from .base_images import (
    clear_diff_texture,
    upload_image,
    upload_pil_images,
)


def set_background(widget, pixmap: QPixmap | None):
    widget.runtime_state._background_pixmap = pixmap
    if pixmap:
        upload_image(widget, pixmap.toImage(), 0)
    widget.update()


def set_layers(
    widget,
    background: QPixmap | None,
    overlay: QPixmap | None,
    overlay_pos: QPoint | None,
    coords_snapshot=None,
):
    if background is not None:
        set_background(widget, background)
    else:
        widget.runtime_state._background_pixmap = None
    set_feature_overlay_content(widget, overlay, overlay_pos)


def set_pil_layers(
    widget,
    pil_image1=None,
    pil_image2=None,
    overlay=None,
    overlay_pos=None,
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

    if overlay:
        pixmap = QPixmap.fromImage(
            QImage(
                overlay.tobytes("raw", "RGBA"),
                overlay.width,
                overlay.height,
                QImage.Format.Format_RGBA8888,
            )
        )
        set_feature_overlay_content(widget, pixmap, overlay_pos)
    else:
        widget.update()


def set_pixmap(widget, pixmap: QPixmap | None):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
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
        clear_feature_overlay_gpu(widget)
        state._capture_center = None
        state._capture_radius = 0
        overlay._centers = []
        overlay._radius = 0
        state._content_rect_px = (0, 0, max(1, pixmap.width()), max(1, pixmap.height()))
        state._clip_overlays_to_content_rect = False
    else:
        set_layers(widget, None, None, None, None)


def clear(widget):
    state = widget.runtime_state
    overlay = state._feature_overlay_gpu
    state._background_pixmap = None
    overlay._pixmap = None
    overlay._top_left = None
    overlay._centers = []
    overlay._radius = 0.0
    overlay._quads = []
    overlay._use_circle_mask = []
    overlay._gpu_active = False
    overlay._gpu_slots = []
    overlay._gpu_widget_geometry_sig = None
    state._images_uploaded = [False, False]
    state._stored_image_ids = None
    state._stored_pil_images = [None, None]
    state._source_pil_images = [None, None]
    state._source_image_ids = [0, 0]
    state._source_images_ready = False
    state._diff_source_pil_image = None
    state._diff_source_image_id = 0
    state._diff_source_ready = False
    state._source_preload_scheduled = False
    state._shader_letterbox_mode = False
    state._content_rect_px = None
    state._inner_content_rect_px = None
    state._inner_split_position = None
    state._clip_overlays_to_content_rect = False
    state._content_scissor_depth = 0
    state._letterbox_params = [None, None]
    state._canvas_frame_letterbox = None
    state._letterbox_fill_rgba = None
    state._store = None
    state._feature_overlay_quad_ndc = None
    state._capture_center = None
    state._capture_radius = 0.0
    state._capture_circles = []
    state._guide_sets = []
    state._hidden_capture_circles = []
    state._occluded_capture_arcs = []
    state._hidden_overlay_circles = []
    state._drag_overlay_visible = False
    state._drag_overlay_horizontal = False
    state._drag_overlay_texts = ("", "")
    state._drag_overlay_cache_key = None
    state._drag_overlay_cached_image = None
    state._paste_overlay_visible = False
    state._paste_overlay_horizontal = False
    state._paste_overlay_hovered_button = None
    state._pending_texture_uploads.clear()
    cache = getattr(state, "_texture_upload_cache", None)
    if cache is not None:
        cache.clear()
    clear_diff_texture(widget)
    clear_feature_overlay_gpu(widget)
    widget.update()
