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

@dataclass(slots=True)
class ExportSaveContext:
    original1_full: object
    original2_full: object
    image1_for_save: object
    image2_for_save: object
    render_plan: object | None
    render_store: object | None
    preview_img: object | None
    suggested_filename: str
    native_width: int = 0
    native_height: int = 0
