from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FilenameOverlayStyle:
    font_pixel_size: int = 18
    label_safe_gap_px: float = 8.0
    label_padding_x_px: float = 10.0
    label_padding_y_px: float = 6.0
    glyph_overscan_px: float = 2.0
    label_corner_radius_px: float = 6.0
    text_inset_px: float = 10.0
    text_alpha: float = 1.0
