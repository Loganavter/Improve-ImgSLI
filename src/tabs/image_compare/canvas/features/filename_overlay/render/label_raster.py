from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from ui.canvas_presentation.filename_labels import (
    draw_round_rect,
    draw_text_bold,
    fit_text,
)
from ui.canvas_presentation.label_style import FilenameOverlayStyle
from ui.canvas_infra.rhi.render_common import new_overlay_image

# Must match shaders/label_downsample.frag's own `SCALE` constant (kept in
# sync by comment on both sides, same convention as
# shared.rendering.glass_panel._TEXT_MASK_SUPERSAMPLE). rasterize_label()
# rasterizes the *entire* label (background rect + text) at this multiple
# of its own final device resolution and returns it undownscaled; the GPU
# downsample pass in render/gpu_resources.py resolves it back down to final
# size with a Lanczos-2 kernel -- see that pass's own docstring, and
# docs/dev/rendering/glass-panel-text-vibrancy-plan.md's bug 18 for why this
# replaced an earlier per-call CPU downscale (PIL LANCZOS when available,
# Qt's own lower-quality implicit scale otherwise).
_LABEL_SUPERSAMPLE = 4


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
) -> tuple[QImage, QSize]:
    """Rasterizes the entire label (background rect + text) at
    ``_LABEL_SUPERSAMPLE`` x its own final device resolution and returns it
    *undownscaled*, alongside that final device-px size -- see this
    module's ``_LABEL_SUPERSAMPLE`` docstring for why (the caller's GPU
    downsample pass does the actual downscale)."""
    dpr = max(1.0, float(dpr))
    phys_w = max(1, int(round(rw * dpr)))
    phys_h = max(1, int(round(rh * dpr)))
    total_scale = dpr * _LABEL_SUPERSAMPLE
    super_w = max(1, int(round(rw * total_scale)))
    super_h = max(1, int(round(rh * total_scale)))
    img = new_overlay_image(super_w, super_h)
    painter = QPainter(img)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(total_scale, total_scale)
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
            draw_text_bold(
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
    return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied), QSize(
        phys_w, phys_h
    )
