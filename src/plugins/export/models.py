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

@dataclass(slots=True)
class ExportSaveContext:
    original1_full: object
    original2_full: object
    image1_for_save: object
    image2_for_save: object
    magnifier_coords_for_save: object
    render_context: object
    preview_img: object | None
    suggested_filename: str

@dataclass(slots=True)
class ExportRenderContext:
    image1: object
    image2: object
    width: int
    height: int
    source_image1: object
    source_image2: object
    source_key: object
    magnifier_drawing_coords: object | None
    prepared_background_layers: tuple[object, object] | None
    cached_diff_image: object | None
