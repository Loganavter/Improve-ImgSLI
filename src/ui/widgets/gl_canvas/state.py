from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPixmap, QSurfaceFormat

@dataclass(slots=True)
class GLCanvasRuntimeState:
    _background_pixmap: QPixmap | None = None
    _magnifier_pixmap: QPixmap | None = None
    _magnifier_top_left: QPoint | None = None
    _capture_center: QPointF | None = None
    _capture_radius: float = 0.0
    _magnifier_centers: list[QPointF] = field(default_factory=list)
    _magnifier_radius: float = 0.0
    _magnifier_border_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 248)
    )
    _magnifier_border_width: float = 2.0
    _show_divider: bool = False
    _split_pos: int = 0
    _is_horizontal_split: bool = False
    _divider_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    _divider_thickness: int = 2
    _capture_color: QColor = field(default_factory=lambda: QColor(255, 50, 100, 230))
    _show_guides: bool = False
    _laser_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 120))
    _guides_thickness: int = 1
    _images_uploaded: list[bool] = field(default_factory=lambda: [False, False])
    _stored_pil_images: list = field(default_factory=lambda: [None, None])
    _source_pil_images: list = field(default_factory=lambda: [None, None])
    _source_image_ids: list = field(default_factory=lambda: [0, 0])
    _source_images_ready: bool = False
    _diff_source_pil_image: object | None = None
    _diff_source_image_id: int = 0
    _diff_source_ready: bool = False
    _source_preload_scheduled: bool = False
    _shader_letterbox_mode: bool = False
    _content_rect_px: tuple[int, int, int, int] | None = None
    _clip_overlays_to_content_rect: bool = False
    _content_scissor_depth: int = 0
    _mag_quads: list = field(default_factory=lambda: [None, None, None])
    _mag_use_circle_mask: list[bool] = field(default_factory=lambda: [True, True, True])
    _mag_combined_params: list = field(default_factory=lambda: [None, None, None])
    _circle_mask_overlay_image: object | None = None
    _circle_mask_shadow_image: object | None = None
    _circle_mask_shadow_cache: dict = field(default_factory=dict)
    _mag_quad_ndc: tuple[float, float, float, float] | None = None
    _mag_gpu_active: bool = False
    _mag_gpu_slots: list = field(default_factory=lambda: [None, None, None])
    _mag_gpu_channel_mode: int = 0
    _mag_gpu_diff_mode: int = 0
    _mag_gpu_diff_threshold: float = 20.0 / 255.0
    _mag_gpu_interp_mode: int = 1
    _letterbox_params: list = field(default_factory=lambda: [None, None])
    _store: object | None = None
    _render_scene: object | None = None
    _split_position_sync: object | None = None
    _apply_channel_mode_in_shader: bool = True
    _update_batch_depth: int = 0
    _update_pending: bool = False
    _drag_overlay_visible: bool = False
    _drag_overlay_horizontal: bool = False
    _drag_overlay_texts: tuple[str, str] = ("", "")
    _drag_overlay_cache_key: object | None = None
    _drag_overlay_cached_image: object | None = None
    _filename_overlay_cache_key: object | None = None
    _filename_overlay_cached_image: object | None = None
    _paste_overlay_visible: bool = False
    _paste_overlay_horizontal: bool = False
    _paste_overlay_texts: dict = field(
        default_factory=lambda: {"up": "", "down": "", "left": "", "right": ""}
    )
    _paste_overlay_hovered_button: object | None = None
    _paste_overlay_button_size: float = 120.0
    _paste_overlay_spacing: float = 20.0
    _paste_overlay_center_size: float = 60.0
    _paste_overlay_rects: dict = field(
        default_factory=lambda: {
            "up": QRectF(),
            "down": QRectF(),
            "left": QRectF(),
            "right": QRectF(),
            "cancel": QRectF(),
        }
    )

def init_widget_state(widget):
    widget.setMouseTracking(True)

    widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    widget.setAutoFillBackground(True)

    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
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

    widget.shader_program = None
    widget.vao = None
    widget.vbo = None
    widget.textures = [None, None]

    widget.texture_ids = [0, 0]
    widget._source_texture_ids = [0, 0]
    widget._diff_source_texture_id = 0
    widget._mag_shader_cache = {}
    widget._mag_tex_ids = [0, 0, 0]
    widget._mag_combined_tex_ids = [0, 0, 0]
    widget._circle_mask_tex_id = 0
    widget._mag_tex_id = 0

    widget._circle_shader = None
    widget._guides_tex_id = 0
    widget._ui_overlay_tex_id = 0

    widget.runtime_state = GLCanvasRuntimeState()
