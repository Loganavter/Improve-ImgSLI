from __future__ import annotations

from dataclasses import dataclass

from domain.types import Color

@dataclass(slots=True)
class ExportDialogState:
    current_language: str
    output_dir: str
    favorite_dir: str | None
    last_format: str
    quality: int
    png_compress_level: int
    fill_background: bool
    background_color: Color | None
    comment_text: str
    comment_keep_default: bool
    resolution_scale: float = 1.0
    # Image Compare: only when magnifier/uncrop grew the canvas past 0..1.
    # Multi Compare keeps True so transparent formats can still fill empty slots.
    virtual_canvas_active: bool = True
