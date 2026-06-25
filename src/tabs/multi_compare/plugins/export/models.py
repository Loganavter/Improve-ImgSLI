"""Models for the Multi Compare export plugin."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(slots=True)
class MultiCompareExportDialogState:
    current_language: str
    output_dir: str
    favorite_dir: str | None
    last_format: str
    quality: int
    png_compress_level: int
    fill_background: bool
    background_color: QColor
    comment_text: str = ""
    comment_keep_default: bool = False
    resolution_scale: float = 1.0
