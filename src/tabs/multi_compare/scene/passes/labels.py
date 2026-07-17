"""Filename label overlay painter for Multi Compare."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter

from tabs.multi_compare.ui.layer_labels import LayerLabelStyle, paint_layer_label
from ui.widgets.canvas.render_metrics import resolve_relative_px


class LabelsOverlaySource:
    """Paints per-layer filename labels into the shared overlay image.

    Geometry comes from ``composition.layers`` and styling from
    ``composition.label_settings`` — both baked into the immutable
    ``ResolvedComposition`` at plan-build time, so live and offscreen-export
    rendering read identical settings without needing a populated widget/state.
    """

    LABEL_FONT_PX = 32

    LABEL_PADDING_X_PX = 10.0
    LABEL_PADDING_Y_PX = 6.0
    LABEL_CORNER_RADIUS_PX = 6.0
    LABEL_SAFE_GAP_PX = 8.0
    LABEL_TEXT_INSET_PX = 10.0
    LABEL_GLYPH_OVERSCAN_PX = 2.0

    def should_paint(self, composition) -> bool:
        return bool(
            composition is not None
            and any(
                layer.label is not None and layer.label.text
                for layer in composition.layers
            )
        )

    def paint(
        self,
        painter: QPainter,
        *,
        composition,
        scale: float,
        offset: tuple[float, float],
        framebuffer_size: tuple[float, float],
    ) -> None:
        if composition is None:
            return
        ox, oy = offset
        fb_w, fb_h = framebuffer_size
        short_edge_fb = min(max(0.0, float(fb_w)), max(0.0, float(fb_h)))
        style = self._resolve_label_style(
            getattr(composition, "label_settings", None), short_edge_fb=short_edge_fb
        )
        for layer in composition.layers:
            if layer.label is None or not layer.label.text:
                continue
            lx, ly, lw, lh = layer.rect
            paint_layer_label(
                painter,
                cell_rect_fb=(
                    ox + lx * scale,
                    oy + ly * scale,
                    lw * scale,
                    lh * scale,
                ),
                text=layer.label.text,
                style=style,
            )

    def _resolve_label_style(
        self, settings=None, *, short_edge_fb: float = 1000.0
    ) -> LayerLabelStyle:
        size_percent = int(getattr(settings, "font_size_percent", 100) or 100)
        alpha_percent = int(getattr(settings, "text_alpha_percent", 100) or 100)
        text_rgba = getattr(settings, "text_rgba", (255, 255, 255, 255))
        bg_rgba = getattr(settings, "bg_rgba", (0, 0, 0, 170))
        draw_background = bool(getattr(settings, "draw_background", True))
        alpha_mult = alpha_percent / 100.0
        text_color = QColor(*text_rgba)
        text_color.setAlpha(max(0, min(255, int(text_color.alpha() * alpha_mult))))
        if draw_background:
            bg_color = QColor(*bg_rgba)
            bg_color.setAlpha(max(0, min(255, int(bg_color.alpha() * alpha_mult))))
        else:
            bg_color = QColor(0, 0, 0, 0)
        # All *_PX constants above are "du" (design units) against a 1000px
        # reference short edge — same convention as image_compare's
        # style_tokens.py (filename_label_padding_x_du etc, which use these
        # exact numbers). They must scale with the *current render target*
        # (framebuffer_size — small for the live preview, large for export),
        # not with the composition's fixed native canvas size, mirroring how
        # image_compare's RenderMetrics.content_width/height is the live
        # widget/export framebuffer size, not the source image resolution.
        def _du(value: float) -> float:
            return resolve_relative_px(value, short_edge_px=short_edge_fb)

        return LayerLabelStyle(
            font_pixel_size_fb=max(
                1,
                int(round(_du(self.LABEL_FONT_PX * size_percent / 100.0))),
            ),
            padding_x_fb=_du(self.LABEL_PADDING_X_PX),
            padding_y_fb=_du(self.LABEL_PADDING_Y_PX),
            corner_radius_fb=_du(self.LABEL_CORNER_RADIUS_PX),
            safe_gap_fb=_du(self.LABEL_SAFE_GAP_PX),
            text_inset_fb=_du(self.LABEL_TEXT_INSET_PX),
            glyph_overscan_fb=_du(self.LABEL_GLYPH_OVERSCAN_PX),
            text_color=text_color,
            bg_color=bg_color,
            font_weight=max(0, int(getattr(settings, "font_weight", 0) or 0)),
        )
