import numpy as np
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPixmap, QSurfaceFormat

def init_widget_state(widget):
    widget.setMouseTracking(True)

    widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(0)
    widget.setFormat(fmt)

    widget._quad_vertices = np.array(
        [
            -1.0, 1.0, 0.0, 0.0,
            -1.0, -1.0, 0.0, 1.0,
            1.0, 1.0, 1.0, 0.0,
            1.0, -1.0, 1.0, 1.0,
        ],
        dtype=np.float32,
    )

    widget.split_position = 0.5
    widget.is_horizontal = False

    widget.zoom_level = 1.0
    widget.pan_offset_x = 0.0
    widget.pan_offset_y = 0.0

    widget._background_pixmap: QPixmap | None = None
    widget._magnifier_pixmap: QPixmap | None = None
    widget._magnifier_top_left: QPoint | None = None

    widget._capture_center: QPointF | None = None
    widget._capture_radius: float = 0

    widget._magnifier_centers: list[QPointF] = []
    widget._magnifier_radius: float = 0
    widget._magnifier_border_color: QColor = QColor(255, 255, 255, 248)
    widget._magnifier_border_width: float = 2.0

    widget._show_divider = False
    widget._split_pos = 0
    widget._is_horizontal_split = False
    widget._divider_color = QColor(255, 255, 255, 255)
    widget._divider_thickness = 2

    widget._capture_color = QColor(255, 50, 100, 230)
    widget._show_guides = False
    widget._laser_color = QColor(255, 255, 255, 120)
    widget._guides_thickness = 1

    widget.shader_program = None
    widget.vao = None
    widget.vbo = None
    widget.textures = [None, None]

    widget.texture_ids = [0, 0]
    widget._source_texture_ids = [0, 0]
    widget._images_uploaded = [False, False]
    widget._stored_pil_images = [None, None]
    widget._source_pil_images = [None, None]
    widget._source_image_ids = [0, 0]
    widget._source_images_ready = False
    widget._source_preload_scheduled = False
    widget._shader_letterbox_mode = False
    widget._content_rect_px = None
    widget._clip_overlays_to_content_rect = False

    widget._mag_shader = None
    widget._mag_tex_ids = [0, 0, 0]
    widget._mag_quads = [None, None, None]
    widget._mag_use_circle_mask = [True, True, True]
    widget._mag_combined_tex_ids = [0, 0, 0]
    widget._mag_combined_params = [None, None, None]
    widget._circle_mask_tex_id = 0
    widget._circle_mask_overlay_image = None
    widget._circle_mask_shadow_image = None
    widget._circle_mask_shadow_cache = {}
    widget._mag_tex_id = 0
    widget._mag_quad_ndc = None

    widget._mag_gpu_active = False
    widget._mag_gpu_slots = [None, None, None]
    widget._mag_gpu_channel_mode = 0
    widget._mag_gpu_diff_mode = 0
    widget._mag_gpu_diff_threshold = 20.0 / 255.0
    widget._mag_gpu_interp_mode = 1
    widget._letterbox_params = [None, None]

    widget._circle_shader = None
    widget._guides_tex_id = 0
    widget._ui_overlay_tex_id = 0

    widget._store = None
    widget._apply_channel_mode_in_shader = True
    widget._update_batch_depth = 0
    widget._update_pending = False
    widget._drag_overlay_visible = False
    widget._drag_overlay_horizontal = False
    widget._drag_overlay_texts = ("", "")
    widget._drag_overlay_cache_key = None
    widget._drag_overlay_cached_image = None
    widget._paste_overlay_visible = False
    widget._paste_overlay_horizontal = False
    widget._paste_overlay_texts = {
        "up": "",
        "down": "",
        "left": "",
        "right": "",
    }
    widget._paste_overlay_hovered_button = None
    widget._paste_overlay_button_size = 120.0
    widget._paste_overlay_spacing = 20.0
    widget._paste_overlay_center_size = 60.0
    widget._paste_overlay_rects = {
        "up": QRectF(),
        "down": QRectF(),
        "left": QRectF(),
        "right": QRectF(),
        "cancel": QRectF(),
    }
