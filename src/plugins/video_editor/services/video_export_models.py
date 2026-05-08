from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

def unique_video_path(directory: str, base_name: str, ext: str) -> str:
    full_path = f"{directory}/{base_name}.{ext}"
    import os

    if not os.path.exists(full_path):
        return full_path
    counter = 1
    while True:
        new_path = f"{directory}/{base_name} ({counter}).{ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1

@dataclass(slots=True, frozen=True)
class GlobalCanvasBounds:
    pad_left: int
    pad_right: int
    pad_top: int
    pad_bottom: int
    base_width: int
    base_height: int

    def as_tuple(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.pad_left,
            self.pad_right,
            self.pad_top,
            self.pad_bottom,
            self.base_width,
            self.base_height,
        )

@dataclass(slots=True, frozen=True)
class VideoRenderRequest:
    output_width: int
    output_height: int
    font_path: str | None
    auto_crop: bool
    fit_content: bool
    global_bounds: GlobalCanvasBounds | None
    fill_rgba: tuple[int, int, int, int]

@dataclass(slots=True, frozen=True)
class RenderedFrame:
    image: Image.Image
    backend: str
    debug: dict

@dataclass(slots=True)
class VideoExportJob:
    recording: object
    output_path: str
    width: int
    height: int
    fps: int
    total_frames: int
    font_path: str | None
    fit_content: bool
    fill_rgba: tuple[int, int, int, int]
    global_bounds: GlobalCanvasBounds | None
    auto_crop: bool
    export_options: dict

@dataclass(slots=True)
class FrameTimingStats:
    evaluate_ms: float = 0.0
    render_ms: float = 0.0
    resize_ms: float = 0.0
    ffmpeg_write_ms: float = 0.0
    total_ms: float = 0.0
    frames: int = 0

    def add(
        self,
        *,
        evaluate_ms: float,
        render_ms: float,
        resize_ms: float,
        ffmpeg_write_ms: float,
        total_ms: float,
    ) -> None:
        self.evaluate_ms += evaluate_ms
        self.render_ms += render_ms
        self.resize_ms += resize_ms
        self.ffmpeg_write_ms += ffmpeg_write_ms
        self.total_ms += total_ms
        self.frames += 1

    def avg(self, value: float) -> float:
        return value / self.frames if self.frames else 0.0
