from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPalette

from shared.rendering.screen_projection import (
    ndc_rect_from_screen_disk as ndc_rect_from_screen_disk,
)
from shared.rendering.screen_projection import project_px_to_screen
from ui.canvas_infra.viewport.state import (
    get_pan_offset_x,
    get_pan_offset_y,
    get_zoom_level,
)


def widget_px_to_screen_px(
    widget,
    px_x,
    px_y,
    canvas_width=None,
    canvas_height=None,
    canvas_offset_x=0.0,
    canvas_offset_y=0.0,
):
    """Accessor for ``project_px_to_screen``: pulls this widget's zoom/pan
    from ``ui.canvas_infra.viewport.state`` (one pair per widget) instead
    of taking them as arguments. A caller with a differently-shaped
    zoom/pan model (e.g. one pair per slot instead of per widget) should
    call ``shared.rendering.screen_projection.project_px_to_screen``
    directly with its own values rather than adapting to this signature.

    ``canvas_width``/``canvas_height`` default to the actual widget size (the
    live/interactive case, where canvas == render target). Tiled export
    passes the full logical canvas size here plus the current tile's
    top-left as ``canvas_offset_x/y``, so the same pan/zoom formula holds
    while the render target is only a tile's worth of pixels.
    """
    w = canvas_width if canvas_width is not None else widget.width()
    h = canvas_height if canvas_height is not None else widget.height()
    return project_px_to_screen(
        px_x,
        px_y,
        w,
        h,
        get_zoom_level(widget),
        get_pan_offset_x(widget),
        get_pan_offset_y(widget),
        canvas_offset_x=canvas_offset_x,
        canvas_offset_y=canvas_offset_y,
    )



def should_render_blank_white(scene_frame) -> bool:
    return bool(getattr(scene_frame, "blank_white", False))


def new_overlay_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGBA8888_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image