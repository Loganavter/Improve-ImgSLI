from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple

from shared.video_policy import CrfPolicy

if TYPE_CHECKING:
    from core.main_controller import MainController
    from core.session_manager import SessionManager
    from core.store import Store


@dataclass
class VideoProjectModel:

    width: int = 1920
    height: int = 1080

    # Fps mirror (ve-p3): owner is PlaybackEngine; this field is written by
    # the fps controls and seeded at dialog init. Export reads the editor
    # mirror (frame-math truth); keep all three in sync via the engine.
    fps: int = 60
    preview_render_scale: float = 1.0

    aspect_ratio_locked: bool = True
    original_ratio: float = 16 / 9

    container: str = "mp4"
    codec: str = "h264"
    quality_mode: str = "crf"
    crf: int = CrfPolicy.DEFAULT
    bitrate: str = "8000k"
    preset: str = "medium"
    pix_fmt: str = "yuv420p"

    manual_mode: bool = False
    manual_args: str = "-c:v libx264 -crf 23 -pix_fmt yuv420p"

    def get_resolution(self) -> Tuple[int, int]:
        return self.width, self.height

    def set_resolution(self, width: int, height: int):
        self.width = width
        self.height = height
        # Always refresh the locked ratio from the absolute size. Leaving the
        # default 16:9 after bootstrap from 4:3 sources made width edits (and
        # some export paths) snap to the wrong DAR.
        if height > 0:
            self.original_ratio = width / height

    def adjust_height_to_aspect_ratio(self, width: int) -> int:
        if not self.aspect_ratio_locked or self.original_ratio <= 0:
            return self.height

        new_height = int(width / self.original_ratio)

        if new_height % 2 != 0:
            new_height += 1
        return new_height

    def adjust_width_to_aspect_ratio(self, height: int) -> int:
        if not self.aspect_ratio_locked or self.original_ratio <= 0:
            return self.width

        new_width = int(height * self.original_ratio)

        if new_width % 2 != 0:
            new_width += 1
        return new_width