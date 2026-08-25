from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path

from PIL import Image
from shared.image_processing.pil_save import next_available_path
from shared.rendering import NormalizedBounds, TargetSurfaceSpec, VirtualCanvasLayout


def unique_video_path(directory: str, base_name: str, ext: str) -> str:
    # Single source: shared/image_processing/pil_save.py:45 next_available_path
    # Fixed f-string path (was f"{directory}/{...}") → pathlib.
    candidate = Path(directory) / f"{base_name}.{ext.lstrip('.')}"
    return str(next_available_path(candidate, style="paren"))

@dataclass(slots=True, frozen=True)
class GlobalCanvasBounds:
    pad_left: int
    pad_right: int
    pad_top: int
    pad_bottom: int
    base_width: int
    base_height: int
    canvas_x_min: float = 0.0
    canvas_x_max: float = 1.0
    canvas_y_min: float = 0.0
    canvas_y_max: float = 1.0

    def extends_beyond_unit(self, *, eps: float = 1e-9) -> bool:
        """True when the resolved virtual canvas leaves normalized ``0..1``.

        Fill-background only paints those pads; with a unit canvas the option
        is meaningless and must stay off in the still-image exporter.
        """
        return (
            float(self.canvas_x_min) < -eps
            or float(self.canvas_x_max) > 1.0 + eps
            or float(self.canvas_y_min) < -eps
            or float(self.canvas_y_max) > 1.0 + eps
            or int(self.pad_left) > 0
            or int(self.pad_right) > 0
            or int(self.pad_top) > 0
            or int(self.pad_bottom) > 0
        )

    def to_virtual_layout(self) -> VirtualCanvasLayout:
        return VirtualCanvasLayout(
            canvas_bounds=NormalizedBounds(
                x_min=float(self.canvas_x_min),
                x_max=float(self.canvas_x_max),
                y_min=float(self.canvas_y_min),
                y_max=float(self.canvas_y_max),
            ),
            content_bounds=NormalizedBounds.unit(),
        )

@dataclass(slots=True, frozen=True)
class VideoRenderRequest:
    target_surface: TargetSurfaceSpec
    font_path: str | None
    auto_crop: bool
    fit_content: bool
    global_bounds: GlobalCanvasBounds | None

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