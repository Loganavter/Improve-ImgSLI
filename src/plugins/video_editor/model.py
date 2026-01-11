

from dataclasses import dataclass
from typing import Tuple

@dataclass
class VideoProjectModel:

    width: int = 1920
    height: int = 1080

    fps: int = 60

    aspect_ratio_locked: bool = True
    original_ratio: float = 16/9

    container: str = "mp4"
    codec: str = "h264"
    quality_mode: str = "crf"
    crf: int = 23
    bitrate: str = "8000k"
    preset: str = "medium"

    manual_mode: bool = False
    manual_args: str = "-c:v libx264 -crf 23 -pix_fmt yuv420p"

    def get_resolution(self) -> Tuple[int, int]:
        return self.width, self.height

    def set_resolution(self, width: int, height: int):
        self.width = width
        self.height = height

        if not self.aspect_ratio_locked and height > 0:
            self.original_ratio = width / height

    def get_aspect_ratio(self) -> float:
        if self.height > 0:
            return self.width / self.height
        return 16/9

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

