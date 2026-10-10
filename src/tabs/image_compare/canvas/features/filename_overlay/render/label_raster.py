"""CPU raster + per-slot screen quads for the filename_overlay pass.

F5 BOUNDARY (stays): the ``_LABEL_SUPERSAMPLE`` supersampled upload and
the per-slot ``build_quad_vertices`` screen quads below are two of the
five stays in the filename verdict (full statement on
``FilenameOverlayPass``; mechanical pins in
``src/tabs/image_compare/tests/render/test_filename_boundary.py``).
A single-fullscreen-upload shell has no supersample stage and no
per-slot quads, so this module's output shape cannot ride it; MC
``layer_labels`` rides the shell only because it rasters one fullscreen
frame with no supersampling.
"""

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
    """Per-slot screen quad for one label rect (BOUNDARY, F5).

    Emits one NDC TriangleStrip quad sized to ``rect`` -- never the
    shared ``FULLSCREEN_VERTICES`` the ``TexturedOverlayShell`` stages.
    """
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
    supersample: int = _LABEL_SUPERSAMPLE,
) -> tuple[QImage, QSize]:
    """Rasterizes the entire label (background rect + text) at
    ``supersample`` x its own final device resolution and returns it
    *undownscaled*, alongside that final device-px size -- see this
    module's ``_LABEL_SUPERSAMPLE`` docstring for why (the caller's GPU
    downsample pass does the actual downscale).

    ``supersample`` defaults to ``_LABEL_SUPERSAMPLE`` (4). The overlay pass
    passes ``1`` while an interactive drag is in flight: that rasterizes
    straight to device resolution (no supersample), which the pass uploads
    into the final texture and draws directly (skipping the Lanczos pass) --
    ~16x cheaper, so the label tracks the divider without frame drops. The
    settled frame re-rasterizes at the full 4x for crispness.

    BOUNDARY (F5): this supersampled-upload shape is the stay the shell
    cannot host -- the shell uploads device-res bytes and draws them in
    the same main pass, with no Lanczos pre-pass stage in between.
    """
    dpr = max(1.0, float(dpr))
    supersample = max(1, int(supersample))
    phys_w = max(1, int(round(rw * dpr)))
    phys_h = max(1, int(round(rh * dpr)))
    total_scale = dpr * supersample
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
