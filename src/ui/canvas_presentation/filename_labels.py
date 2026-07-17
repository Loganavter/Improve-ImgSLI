from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

from ui.canvas_presentation.label_style import FilenameOverlayStyle
from ui.widgets.canvas.render_common import new_overlay_image


def qcolor(value, fallback: QColor) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if value is not None and all(hasattr(value, attr) for attr in ("r", "g", "b", "a")):
        return QColor(int(value.r), int(value.g), int(value.b), int(value.a))
    return QColor(fallback)


def font_for_style(widget, style: FilenameOverlayStyle) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(int(style.font_pixel_size))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def snap_rect_to_pixels(rect: QRectF | None) -> QRectF | None:
    if rect is None:
        return None
    x = int(round(rect.left()))
    y = int(round(rect.top()))
    w = max(1, int(round(rect.width())))
    h = max(1, int(round(rect.height())))
    return QRectF(float(x), float(y), float(w), float(h))


def label_rects(
    cfg,
    content_rect,
    font_metrics: QFontMetrics,
    name1: str,
    name2: str,
    style: FilenameOverlayStyle,
    split_override: float | None = None,
    divider_thickness_wx: float | None = None,
):
    x, y, w, h = content_rect
    safe_gap = float(style.label_safe_gap_px)
    padding_x = float(style.label_padding_x_px)
    padding_y = float(style.label_padding_y_px)
    glyph_overscan = float(style.glyph_overscan_px)
    label_h = float(font_metrics.height()) + padding_y * 2.0
    min_text_w = float(font_metrics.horizontalAdvance("..."))
    min_label_w = padding_x * 2.0 + min_text_w
    raw_split = (
        split_override
        if split_override is not None
        else float(getattr(cfg, "split_position", 0.5))
    )
    split = max(0.0, min(1.0, raw_split))
    is_horizontal = bool(getattr(cfg, "is_horizontal", False))
    placement = str(getattr(cfg, "text_placement_mode", "edges") or "edges")
    if divider_thickness_wx is not None:
        half_line = divider_thickness_wx / 2.0
    else:
        divider = max(0, int(getattr(cfg, "divider_thickness", 0) or 0))
        half_line = float((divider + 1) // 2)

    def rect_for(text: str, max_w: float, anchor_x: float, anchor_y: float, align: str):
        if not text or max_w < min_label_w:
            return None
        preferred_w = (
            float(font_metrics.horizontalAdvance(text))
            + padding_x * 2.0
            + glyph_overscan
        )
        text_w = max(1.0, min(max_w, preferred_w))
        if align == "right":
            left = anchor_x - text_w
        elif align == "center":
            left = anchor_x - (text_w / 2.0)
        else:
            left = anchor_x
        left = max(float(x), min(left, float(x + w) - text_w))
        top = max(float(y), min(anchor_y, float(y + h) - label_h))
        return QRectF(left, top, max(1.0, text_w), label_h)

    if is_horizontal:
        split_y = y + h * split
        max_w = max(1.0, float(w) - safe_gap * 2.0)
        if placement == "split_line":
            y1 = split_y - half_line - safe_gap - label_h
            y2 = split_y + half_line + safe_gap
        else:
            y1 = float(y) + safe_gap
            y2 = float(y + h) - safe_gap - label_h
        center_x = float(x) + (float(w) / 2.0)
        return (
            rect_for(name1, max_w, center_x, y1, "center"),
            rect_for(name2, max_w, center_x, y2, "center"),
        )

    split_x = x + w * split
    max_left = max(1.0, split_x - float(x) - half_line - safe_gap)
    max_right = max(1.0, float(x + w) - split_x - half_line - safe_gap)
    anchor_y = float(y + h) - safe_gap - label_h
    if placement == "split_line":
        return (
            rect_for(
                name1, max_left, split_x - half_line - safe_gap, anchor_y, "right"
            ),
            rect_for(
                name2, max_right, split_x + half_line + safe_gap, anchor_y, "left"
            ),
        )
    return (
        rect_for(name1, max_left - safe_gap, float(x) + safe_gap, anchor_y, "left"),
        rect_for(
            name2, max_right - safe_gap, float(x + w) - safe_gap, anchor_y, "right"
        ),
    )


def limit_name(text: str, max_name_length: int) -> str:
    if max_name_length <= 0 or len(text) <= max_name_length:
        return text
    return text[:max_name_length]


def draw_round_rect(
    painter: QPainter,
    rect: QRectF,
    color: QColor,
    style: FilenameOverlayStyle,
) -> None:
    path = QPainterPath()
    radius = float(style.label_corner_radius_px)
    path.addRoundedRect(rect, radius, radius)
    painter.fillPath(path, color)


def fit_text(text: str, font_metrics: QFontMetrics, available_width: float) -> str:
    # Compare against the full float width — truncating with int() falsely
    # elides when fractional padding/overscan leaves e.g. advance=141 and
    # available=140.6 after pixel snap.
    if font_metrics.horizontalAdvance(text) <= available_width:
        return text
    return font_metrics.elidedText(
        text, Qt.TextElideMode.ElideRight, max(1, int(available_width))
    )


def draw_text_bold_supersampled(
    painter: QPainter,
    text: str,
    font: QFont,
    color: QColor,
    font_weight: int,
    rw: int,
    rh: int,
    text_inset_px: float,
) -> None:
    from shared_toolkit.ui.managers.font_manager import FontManager

    pixel_size = font.pixelSize()
    scale = 4
    stroke_w = max(0, int((pixel_size / 1000.0) * font_weight * scale))
    fill_rgba = (color.red(), color.green(), color.blue(), color.alpha())
    font_path = FontManager.get_instance().get_current_font_path()

    if font_path:
        try:
            from PIL import Image, ImageDraw
            from PIL import ImageFont as PILImageFont

            pil_font = PILImageFont.truetype(font_path, pixel_size * scale)
            hr_bbox = pil_font.getbbox(text, stroke_width=stroke_w)
            hr_w = max(1, hr_bbox[2] - hr_bbox[0])
            hr_h = max(1, hr_bbox[3] - hr_bbox[1])
            txt_canvas = Image.new("RGBA", (hr_w, hr_h), (0, 0, 0, 0))
            ImageDraw.Draw(txt_canvas).text(
                (-hr_bbox[0], -hr_bbox[1]),
                text,
                fill=fill_rgba,
                font=pil_font,
                stroke_width=stroke_w,
                stroke_fill=fill_rgba,
            )
            final_w = max(1, hr_w // scale)
            final_h = max(1, hr_h // scale)
            txt_small = txt_canvas.resize((final_w, final_h), Image.Resampling.LANCZOS)
            raw = txt_small.tobytes("raw", "RGBA")
            txt_qimg = QImage(
                raw, final_w, final_h, final_w * 4, QImage.Format.Format_RGBA8888
            ).copy()
            paste_x = float(text_inset_px)
            paste_y = float(max(0, (rh - final_h) // 2))
            painter.drawImage(QPointF(paste_x, paste_y), txt_qimg)
            return
        except Exception:
            pass

    big_w, big_h = rw * scale, rh * scale
    big_img = new_overlay_image(big_w, big_h)
    big_painter = QPainter(big_img)
    big_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    big_font = QFont(font)
    big_font.setPixelSize(pixel_size * scale)
    big_metrics = QFontMetrics(big_font)
    baseline_y = (float(big_h) - big_metrics.height()) / 2.0 + big_metrics.ascent()
    stroke_px_qt = float(pixel_size) * font_weight / 500.0 * scale
    path = QPainterPath()
    path.addText(QPointF(float(text_inset_px) * scale, baseline_y), big_font, text)
    pen = QPen(color, stroke_px_qt)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    big_painter.setPen(pen)
    big_painter.setBrush(color)
    big_painter.drawPath(path)
    big_painter.end()
    painter.drawImage(
        QRectF(0.0, 0.0, float(rw), float(rh)),
        big_img,
        QRectF(0.0, 0.0, float(big_w), float(big_h)),
    )
