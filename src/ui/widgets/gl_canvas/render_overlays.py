import math

from PIL import Image
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from shared.image_processing.qt_conversion import pil_to_qimage_zero_copy
from shared_toolkit.ui.managers.font_manager import FontManager

from .render_common import (
    draw_qimage_overlay_texture,
    draw_raster_shape,
    get_rendering_pipeline,
    make_overlay_font,
    new_overlay_image,
)
from .render_config import get_content_rect_screen_px, get_local_visible_image_rect

def build_filename_overlay_image(widget) -> QImage | None:
    state = widget.runtime_state
    store = state._store
    scene = state._render_scene
    filename_cfg = getattr(scene, "filename_overlay", None)
    if store is None or filename_cfg is None or not filename_cfg.enabled:
        return None
    if not getattr(store, "document", None):
        return None

    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None
    if not math.isclose(float(getattr(widget, "zoom_level", 1.0)), 1.0, rel_tol=0.0, abs_tol=1e-6):
        return None

    content_rect = get_content_rect_screen_px(widget)
    if content_rect:
        img_x, img_y, img_w, img_h = content_rect
    else:
        display_rect = filename_cfg.image_display_rect
        if display_rect:
            img_x, img_y, img_w, img_h = display_rect
        else:
            img_x, img_y, img_w, img_h = 0, 0, width, height
    if img_w <= 0 or img_h <= 0:
        return None

    name1 = filename_cfg.name1 or ""
    name2 = filename_cfg.name2 or ""
    if not name1 and not name2:
        return None

    local_content_rect = state._content_rect_px
    logical_img_w = local_content_rect[2] if local_content_rect else img_w
    logical_img_h = local_content_rect[3] if local_content_rect else img_h
    text_placement_mode = str(filename_cfg.text_placement_mode)
    split_value = float(filename_cfg.split_position)
    is_horizontal = bool(filename_cfg.is_horizontal)
    divider_thickness = int(filename_cfg.divider_thickness)
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
        bool(filename_cfg.is_interactive_mode),
        is_horizontal,
        text_layout_key,
        bool(filename_cfg.draw_text_background),
        text_placement_mode,
        int(filename_cfg.font_size_percent),
        int(filename_cfg.font_weight),
        int(filename_cfg.text_alpha_percent),
        filename_cfg.file_name_color,
        filename_cfg.file_name_bg_color,
        name1,
        name2,
    )
    if (
        state._filename_overlay_cache_key == cache_key
        and state._filename_overlay_cached_image is not None
    ):
        return state._filename_overlay_cached_image

    local_visible_rect = get_local_visible_image_rect(
        widget,
        img_x=img_x,
        img_y=img_y,
        img_w=img_w,
        img_h=img_h,
    )
    if local_visible_rect is None:
        return None

    font_path = FontManager.get_instance().get_font_path_for_image_text(store)
    pipeline = get_rendering_pipeline(font_path)
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
    patch_image = pil_to_qimage_zero_copy(patch)
    if patch_image is None or patch_image.isNull():
        return None

    overlay = new_overlay_image(width, height)
    painter = QPainter(overlay)
    try:
        painter.drawImage(QPointF(float(img_x), float(img_y)), patch_image)
    finally:
        painter.end()
    state._filename_overlay_cache_key = cache_key
    state._filename_overlay_cached_image = overlay
    return overlay

def build_drag_overlay_image(widget) -> QImage | None:
    state = widget.runtime_state
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None

    cache_key = (
        width,
        height,
        bool(state._drag_overlay_horizontal),
        tuple(state._drag_overlay_texts),
    )
    if (
        state._drag_overlay_cache_key == cache_key
        and state._drag_overlay_cached_image is not None
    ):
        return state._drag_overlay_cached_image

    margin = 10.0
    half_margin = margin / 2.0
    if state._drag_overlay_horizontal:
        half_height = height / 2.0
        rect1 = QRectF(margin, margin, max(1.0, width - 2.0 * margin), max(1.0, half_height - margin - half_margin))
        rect2 = QRectF(margin, half_height + half_margin, max(1.0, width - 2.0 * margin), max(1.0, half_height - margin - half_margin))
    else:
        half_width = width / 2.0
        rect1 = QRectF(margin, margin, max(1.0, half_width - margin - half_margin), max(1.0, height - 2.0 * margin))
        rect2 = QRectF(half_width + half_margin, margin, max(1.0, half_width - margin - half_margin), max(1.0, height - 2.0 * margin))

    image = new_overlay_image(width, height)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(make_overlay_font(widget, 20))
        for rect, text in zip((rect1, rect2), state._drag_overlay_texts):
            draw_raster_shape(
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
    state._drag_overlay_cache_key = cache_key
    state._drag_overlay_cached_image = image
    return image

def paint_drag_overlay_pass(widget):
    if not widget.runtime_state._drag_overlay_visible:
        return
    overlay = build_drag_overlay_image(widget)
    if overlay is not None:
        draw_qimage_overlay_texture(widget, overlay)

def paint_filename_overlay_pass(widget):
    overlay = build_filename_overlay_image(widget)
    if overlay is not None:
        draw_qimage_overlay_texture(widget, overlay)

def build_paste_overlay_image(widget) -> QImage | None:
    state = widget.runtime_state
    widget._update_paste_overlay_rects()
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return None

    image = new_overlay_image(width, height)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(widget.rect(), QColor(0, 0, 0, 0))

        buttons = []
        if not state._paste_overlay_rects["up"].isNull():
            buttons.append(("up", state._paste_overlay_rects["up"], state._paste_overlay_texts["up"]))
        if not state._paste_overlay_rects["down"].isNull():
            buttons.append(("down", state._paste_overlay_rects["down"], state._paste_overlay_texts["down"]))
        if not state._paste_overlay_rects["left"].isNull():
            buttons.append(("left", state._paste_overlay_rects["left"], state._paste_overlay_texts["left"]))
        if not state._paste_overlay_rects["right"].isNull():
            buttons.append(("right", state._paste_overlay_rects["right"], state._paste_overlay_texts["right"]))

        for direction, rect, text in buttons:
            is_hovered = state._paste_overlay_hovered_button == direction
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

            draw_raster_shape(painter, rect, bg_color, border_color, border_width, 10.0)
            painter.setFont(make_overlay_font(widget, 14 if is_hovered else 12, bold=is_hovered))
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        cancel_rect = state._paste_overlay_rects["cancel"]
        if not cancel_rect.isNull():
            is_hovered = state._paste_overlay_hovered_button == "cancel"
            cancel_bg = QColor(220, 220, 220, 200) if is_hovered else QColor(180, 180, 180, 150)
            draw_raster_shape(
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

def paint_paste_overlay_pass(widget):
    if not widget.runtime_state._paste_overlay_visible:
        return
    overlay = build_paste_overlay_image(widget)
    if overlay is not None:
        draw_qimage_overlay_texture(widget, overlay)
