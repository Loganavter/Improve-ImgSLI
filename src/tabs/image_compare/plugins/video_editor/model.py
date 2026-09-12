from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Tuple

if TYPE_CHECKING:
    from core.main_controller import MainController
    from core.session_manager import SessionManager
    from core.store import Store


@dataclass(frozen=True)
class VideoTimelineState:
    position: int = 0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoTimelineState":
        payload = payload or {}
        return cls(position=max(0, int(payload.get("position", 0))))

    def advance(self, step: int = 1) -> "VideoTimelineState":
        return replace(self, position=max(0, self.position + int(step)))

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position}


@dataclass(frozen=True)
class VideoSelectionState:
    start: int | None = None
    end: int | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoSelectionState":
        payload = payload or {}
        start = payload.get("start")
        end = payload.get("end")
        return cls(
            start=int(start) if start is not None else None,
            end=int(end) if end is not None else None,
        )

    def is_empty(self) -> bool:
        return self.start is None and self.end is None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.start is not None:
            payload["start"] = self.start
        if self.end is not None:
            payload["end"] = self.end
        return payload


@dataclass
class VideoProjectModel:

    width: int = 1920
    height: int = 1080

    fps: int = 60
    preview_render_scale: float = 1.0

    aspect_ratio_locked: bool = True
    original_ratio: float = 16 / 9

    container: str = "mp4"
    codec: str = "h264"
    quality_mode: str = "crf"
    crf: int = 23
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

    def get_aspect_ratio(self) -> float:
        if self.height > 0:
            return self.width / self.height
        return 16 / 9

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