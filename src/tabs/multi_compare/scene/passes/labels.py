"""Filename label overlay painter for Multi Compare."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter

from tabs.multi_compare.ui.layer_labels import LayerLabelStyle, paint_layer_label


class LabelsOverlaySource:
    """Paints per-layer filename labels into the shared overlay image."""

    LABEL_FONT_PX = 32

    LABEL_PADDING_X_PX = 10.0
    LABEL_PADDING_Y_PX = 6.0
    LABEL_CORNER_RADIUS_PX = 6.0
    LABEL_SAFE_GAP_PX = 8.0
    LABEL_TEXT_INSET_PX = 10.0

    def should_paint(self, composition, _state) -> bool:
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
        state,
        scale: float,
        offset: tuple[float, float],
    ) -> None:
        if composition is None:
            return
        ox, oy = offset
        style = self._resolve_label_style(getattr(state, "label_settings", None))
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

    def _resolve_label_style(self, settings=None) -> LayerLabelStyle:
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
        return LayerLabelStyle(
            font_pixel_size_fb=max(
                1, int(round(self.LABEL_FONT_PX * size_percent / 100.0))
            ),
            padding_x_fb=self.LABEL_PADDING_X_PX,
            padding_y_fb=self.LABEL_PADDING_Y_PX,
            corner_radius_fb=self.LABEL_CORNER_RADIUS_PX,
            safe_gap_fb=self.LABEL_SAFE_GAP_PX,
            text_inset_fb=self.LABEL_TEXT_INSET_PX,
            text_color=text_color,
            bg_color=bg_color,
            font_weight=max(0, int(getattr(settings, "font_weight", 0) or 0)),
        )
