from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from ui.canvas_presentation.filename_labels import (
    draw_round_rect,
    draw_text_bold_supersampled,
    fit_text,
)
from ui.canvas_presentation.label_style import FilenameOverlayStyle
from ui.widgets.canvas.render_common import new_overlay_image


def build_quad_vertices(ctx, rect: QRectF) -> bytes:
    w = float(ctx.width)
    h = float(ctx.height)
    x0 = rect.left() / w * 2.0 - 1.0
    x1 = rect.right() / w * 2.0 - 1.0
    y0 = 1.0 - rect.top() / h * 2.0
    y1 = 1.0 - rect.bottom() / h * 2.0
    return struct.pack(
        "<16f",
        x0,
        y0,
        0.0,
        0.0,
        x0,
        y1,
        0.0,
        1.0,
        x1,
        y0,
        1.0,
        0.0,
        x1,
        y1,
        1.0,
        1.0,
    )


def rasterize_label(
    name: str,
    rw: int,
    rh: int,
    font: QFont,
    metrics: QFontMetrics,
    text_color: QColor,
    bg_color: QColor,
    draw_bg: bool,
    style: FilenameOverlayStyle,
    font_weight: int,
    dpr: float,
) -> QImage:
    dpr = max(1.0, float(dpr))
    phys_w = max(1, int(round(rw * dpr)))
    phys_h = max(1, int(round(rh * dpr)))
    img = new_overlay_image(phys_w, phys_h)
    painter = QPainter(img)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(dpr, dpr)
        painter.setFont(font)
        label_rect = QRectF(0.0, 0.0, float(rw), float(rh))
        if draw_bg:
            draw_round_rect(
                painter,
                label_rect.adjusted(0.5, 0.5, -0.5, -0.5),
                bg_color,
                style,
            )
        text_inset = float(style.text_inset_px)
        text_str = fit_text(name, metrics, float(rw) - (text_inset * 2.0))
        if font_weight > 0:
            draw_text_bold_supersampled(
                painter,
                text_str,
                font,
                text_color,
                font_weight,
                rw,
                rh,
                text_inset,
            )
        else:
            painter.setPen(QPen(text_color))
            painter.drawText(
                label_rect.adjusted(text_inset, 0.0, -text_inset, 0.0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text_str,
            )
    finally:
        painter.end()
    return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
