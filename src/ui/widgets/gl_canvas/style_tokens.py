from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class CanvasStyleTokens:
    filename_font_base_du: float = 18.0
    filename_label_safe_gap_du: float = 8.0
    filename_label_padding_x_du: float = 10.0
    filename_label_padding_y_du: float = 6.0
    filename_glyph_overscan_du: float = 2.0
    filename_label_corner_radius_du: float = 6.0
    filename_text_inset_du: float = 10.0
    capture_ring_stroke_du: float = 2.0
    guides_stroke_du: float = 1.0
    occluded_arc_stroke_du: float = 3.0
    hidden_selection_stroke_du: float = 2.0
    overlay_backdrop_alpha: float = 14.0
    overlay_button_inset_du: float = 14.0
    overlay_button_radius_du: float = 10.0
    overlay_button_border_du: float = 1.5
    overlay_button_border_hover_du: float = 2.5
    overlay_button_font_base_du: float = 12.0
    overlay_button_font_hover_base_du: float = 13.0
    overlay_button_visual_width_du: float = 96.0
    overlay_button_visual_height_du: float = 34.0
    overlay_cancel_stroke_du: float = 2.0
    overlay_cancel_icon_du: float = 15.0

DEFAULT_CANVAS_STYLE_TOKENS = CanvasStyleTokens()
