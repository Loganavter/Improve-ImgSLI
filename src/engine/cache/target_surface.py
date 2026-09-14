from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class TargetSurfaceSpec:
    width: int
    height: int
    fill_rgba: tuple[int, int, int, int] | None = None
    output_scale: float = 1.0
    preserve_zoom: bool = False
    clip_overlays_to_image_bounds: bool = False
