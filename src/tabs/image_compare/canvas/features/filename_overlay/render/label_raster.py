"""CPU text-only raster + per-slot screen quads for the filename_overlay pass.

F5 BOUNDARY (variant A, re-opened 2026-10-06): the rounded-rect *background*
is no longer rasterized on the CPU. It is drawn procedurally in
``shaders/filename_overlay.frag`` (a signed-distance rounded box, fed by the
per-slot uniform block's ``quadSizePx`` / ``cornerRadiusPx`` / ``bgColor``),
so the texture this module produces carries ONLY the text on a transparent
background and is cached by CONTENT, never by width. That is the whole point
of variant A: dragging the split divider changes the label quad width every
frame, but the text-only texture is keyed on ``(full_text, elided_text, font,
color, dpr, quality)`` -- it only re-rasterizes when the elided string (or
font/color/dpr) actually changes, not on every width pixel.

The two stays this module still owns are the ones the single-fullscreen-upload
``TexturedOverlayShell`` cannot host: the ``_LABEL_SUPERSAMPLE`` supersampled
text upload and the per-slot ``build_quad_vertices`` screen quads (full
statement on ``FilenameOverlayPass``; mechanical pins in
``src/tabs/image_compare/tests/render/test_filename_boundary.py``). MC
``layer_labels`` rides the shell only because it rasters one pre-composited
fullscreen frame with no supersample stage.
"""

from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from ui.canvas_presentation.filename_labels import draw_text_bold
from ui.canvas_infra.rhi.render_common import new_overlay_image

# Must match shaders/label_downsample.frag's own `SCALE` constant (kept in
# sync by comment on both sides, same convention as
# shared.rendering.glass_panel._TEXT_MASK_SUPERSAMPLE). The text-only raster
# below is drawn at this multiple of its own final device resolution and
# returned undownscaled; the GPU downsample pass in render/gpu_resources.py
# resolves it back down to final size with a Lanczos-2 kernel -- see that
# pass's own docstring, and
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
    font_weight: int,
    dpr: float,
    supersample: float = _LABEL_SUPERSAMPLE,
) -> tuple[QImage, QSize]:
    """Rasterizes the label TEXT ONLY (transparent background) at
    ``supersample`` x its own final device resolution and returns it
    *undownscaled*, alongside that final device-px size. The rounded-rect
    background is drawn later, procedurally, in filename_overlay.frag.

    ``rw``/``rh`` are the text box's own logical size (tight to the glyph
    run, height == the label quad height); the caller derives ``rw`` from the
    elided string's advance, which is what makes the texture width-independent
    (see this module's docstring).

    BOUNDARY (F5): this supersampled text upload shape is the stay the shell
    cannot host -- the shell uploads device-res bytes and draws them in the
    same main pass, with no Lanczos pre-pass stage in between.

    The name ``rasterize_label`` is retained deliberately:
    ``tests/contracts/test_text_paint_scale_scan.py`` allowlists it as
    canvas-scene text that draws with a caller-supplied scene font.
    ``rasterize_label_text`` is the frozen public entry point.
    """
    dpr = max(1.0, float(dpr))
    ss = max(1.0, float(supersample))
    phys_w = max(1, int(round(rw * dpr)))
    phys_h = max(1, int(round(rh * dpr)))
    total_scale = dpr * ss
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
        if font_weight > 0:
            draw_text_bold(painter, name, font, text_color, font_weight, rw, rh, 0.0)
        else:
            painter.setPen(QPen(text_color))
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name,
            )
    finally:
        painter.end()
    return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied), QSize(
        phys_w, phys_h
    )


def rasterize_label_text(
    name: str,
    rw: int,
    rh: int,
    font: QFont,
    metrics: QFontMetrics,
    text_color: QColor,
    font_weight: int,
    dpr: float,
    supersample: float = _LABEL_SUPERSAMPLE,
) -> tuple[QImage, QSize]:
    """Frozen public entry point for the text-only rasterizer (variant A).

    ``name`` is the already-elided string; ``rw``/``rh`` are the tight text
    box's logical size. See ``rasterize_label`` (the retained allowlisted
    name) for the actual raster and the F5 boundary note.
    """
    return rasterize_label(
        name,
        rw,
        rh,
        font,
        metrics,
        text_color,
        font_weight,
        dpr,
        supersample,
    )
