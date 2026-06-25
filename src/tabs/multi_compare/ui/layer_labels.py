"""Per-cell filename labels for the multi-compare overlay.

Reuses the high-quality label rasterization primitives from
:mod:`ui.canvas_features.filename_overlay.labels` so labels look identical to
the ones in main compare: pixel-snapped rounded background, supersampled bold
text, ellipsis on overflow.

The label is positioned at the bottom-left of its layer in framebuffer pixels, so
its visual size is stable regardless of composition canvas scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from ui.canvas_features.filename_overlay.labels import (
    draw_round_rect,
    draw_text_bold_supersampled,
    fit_text,
    snap_rect_to_pixels,
)
from ui.canvas_presentation.render_arch import FilenameOverlayStyle


@dataclass(frozen=True)
class LayerLabelStyle:
    """Subset of FilenameOverlayStyle used by multi-compare cell labels.

    Pixel sizes are in *fb-px* because labels are HUD-like top-layout elements
    with camera-fixed size, not canvas-scaled annotations.
    """

    font_pixel_size_fb: int = 18
    padding_x_fb: float = 10.0
    padding_y_fb: float = 6.0
    corner_radius_fb: float = 6.0
    safe_gap_fb: float = 8.0
    text_inset_fb: float = 10.0
    text_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    bg_color: QColor = field(default_factory=lambda: QColor(0, 0, 0, 170))
    font_weight: int = 0  # 0 → painter's stroke skipped; >0 → bold-supersampled

    def to_filename_overlay_style(self) -> FilenameOverlayStyle:
        return FilenameOverlayStyle(
            font_pixel_size=int(self.font_pixel_size_fb),
            label_safe_gap_px=float(self.safe_gap_fb),
            label_padding_x_px=float(self.padding_x_fb),
            label_padding_y_px=float(self.padding_y_fb),
            glyph_overscan_px=2.0,
            label_corner_radius_px=float(self.corner_radius_fb),
            text_inset_px=float(self.text_inset_fb),
            text_alpha=1.0,
        )


def _font(style: LayerLabelStyle) -> QFont:
    font = QFont()
    font.setPixelSize(int(style.font_pixel_size_fb))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    # Do NOT setBold(True) when font_weight > 0: the bold path renders text via
    # PIL with stroke_width on the *regular* glyphs, so Qt's bold advance would
    # over-estimate label width and leave empty space to the right of the text.
    # Matches image_compare's font_for_style which also keeps the QFont regular.
    return font


def _label_rect_for_cell(
    *,
    cell_rect_fb: tuple[float, float, float, float],
    text: str,
    style: LayerLabelStyle,
) -> QRectF | None:
    if not text:
        return None
    cx, cy, cw, ch = cell_rect_fb
    if cw <= 1 or ch <= 1:
        return None

    font = _font(style)
    fm = QFontMetrics(font)

    max_w = max(1.0, cw - style.safe_gap_fb * 2.0)
    text_w_pref = float(fm.horizontalAdvance(text)) + style.padding_x_fb * 2.0
    label_w = max(1.0, min(max_w, text_w_pref))
    label_h = float(fm.height()) + style.padding_y_fb * 2.0

    left = cx + style.safe_gap_fb
    top = cy + ch - style.safe_gap_fb - label_h
    return snap_rect_to_pixels(QRectF(left, top, label_w, label_h))


def paint_layer_label(
    painter: QPainter,
    *,
    cell_rect_fb: tuple[float, float, float, float],
    text: str,
    style: LayerLabelStyle,
) -> None:
    """Draw ``text`` at the bottom-left of ``cell_rect_fb`` (fb-px)."""
    rect = _label_rect_for_cell(
        cell_rect_fb=cell_rect_fb,
        text=text,
        style=style,
    )
    if rect is None:
        return

    font = _font(style)
    fm = QFontMetrics(font)
    overlay_style = style.to_filename_overlay_style()
    draw_round_rect(painter, rect, style.bg_color, overlay_style)

    inner_w = rect.width() - style.padding_x_fb * 2.0
    fitted = fit_text(text, fm, inner_w)

    painter.save()
    painter.translate(rect.topLeft())
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if style.font_weight > 0:
        draw_text_bold_supersampled(
            painter,
            fitted,
            font,
            style.text_color,
            style.font_weight,
            int(rect.width()),
            int(rect.height()),
            float(style.padding_x_fb),
        )
    else:
        painter.setFont(font)
        painter.setPen(style.text_color)
        text_rect = QRectF(
            style.padding_x_fb,
            0.0,
            inner_w,
            rect.height(),
        )
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), fitted)
    painter.restore()


def layer_label_rect(
    *,
    cell_rect_fb: tuple[float, float, float, float],
    text: str,
    style: LayerLabelStyle,
) -> QRectF | None:
    """Return the label rect inside ``cell_rect_fb`` in framebuffer pixels."""
    return _label_rect_for_cell(
        cell_rect_fb=cell_rect_fb,
        text=text,
        style=style,
    )


def rasterize_layer_label(
    *,
    text: str,
    rect_fb: QRectF,
    style: LayerLabelStyle,
) -> QImage:
    """Rasterize one label into a tight transparent image."""
    width = max(1, int(round(rect_fb.width())))
    height = max(1, int(round(rect_fb.height())))
    img = QImage(width, height, QImage.Format.Format_RGBA8888_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    try:
        local_rect = QRectF(0.0, 0.0, float(width), float(height))
        overlay_style = style.to_filename_overlay_style()
        draw_round_rect(painter, local_rect, style.bg_color, overlay_style)

        font = _font(style)
        fm = QFontMetrics(font)
        inner_w = local_rect.width() - style.padding_x_fb * 2.0
        fitted = fit_text(text, fm, inner_w)
        if style.font_weight > 0:
            draw_text_bold_supersampled(
                painter,
                fitted,
                font,
                style.text_color,
                style.font_weight,
                width,
                height,
                float(style.padding_x_fb),
            )
        else:
            painter.setFont(font)
            painter.setPen(style.text_color)
            text_rect = QRectF(
                style.padding_x_fb,
                0.0,
                inner_w,
                local_rect.height(),
            )
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                fitted,
            )
    finally:
        painter.end()
    return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
