from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain.types import Color

if TYPE_CHECKING:
    from core.store_document import DocumentModel
    from core.store_viewport import ViewportState

@dataclass
class SettingsState:
    current_language: str = "en"
    theme: str = "auto"
    ui_font_mode: str = "builtin"
    ui_font_family: str = ""
    ui_mode: str = "beginner"
    debug_mode_enabled: bool = False
    system_notifications_enabled: bool = True
    auto_crop_black_borders: bool = True
    video_recording_fps: int = 60

    export_use_default_dir: bool = True
    export_default_dir: str | None = None
    export_favorite_dir: str | None = None
    export_video_favorite_dir: str | None = None
    export_video_container: str = "mp4"
    export_video_codec: str = "h264 (AVC)"
    export_video_quality_mode: str = "crf"
    export_video_crf: int = 23
    export_video_bitrate: str = "8000k"
    export_video_preset: str = "medium"
    export_video_pix_fmt: str = "yuv420p"
    export_video_manual_args: str = "-c:v libx264 -crf 23 -pix_fmt yuv420p"
    export_last_format: str = "PNG"
    export_quality: int = 95
    export_fill_background: bool = False
    export_background_color: Color = field(
        default_factory=lambda: Color(255, 255, 255, 255)
    )
    export_last_filename: str = ""
    export_png_compress_level: int = 9
    export_comment_text: str = ""
    export_comment_keep_default: bool = False

    window_width: int = 1024
    window_height: int = 768
    window_x: int = 100
    window_y: int = 100
    window_was_maximized: bool = False

    def freeze_for_export(self):
        return copy.copy(self)

class WorkerStoreSnapshot:
    def __init__(
        self,
        viewport: "ViewportState",
        settings: SettingsState,
        document: "DocumentModel",
    ):
        self.viewport = viewport
        self.settings = settings
        self.document = document
