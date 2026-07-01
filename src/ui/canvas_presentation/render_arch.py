from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RenderIntentKind = Literal["interactive", "preview", "export", "thumbnail"]


@dataclass(frozen=True, slots=True)
class RenderIntent:
    kind: RenderIntentKind
    output_width: int
    output_height: int
    output_scale: float
    zoom_level: float
    clip_overlays_to_content: bool
    preserve_zoom: bool = False


def build_render_intent(
    *,
    kind: RenderIntentKind,
    output_width: int,
    output_height: int,
    output_scale: float,
    zoom_level: float,
    clip_overlays_to_content: bool,
    preserve_zoom: bool = False,
) -> RenderIntent:
    return RenderIntent(
        kind=kind,
        output_width=max(0, int(output_width)),
        output_height=max(0, int(output_height)),
        output_scale=max(0.0, float(output_scale)),
        zoom_level=max(0.0, float(zoom_level)),
        clip_overlays_to_content=bool(clip_overlays_to_content),
        preserve_zoom=bool(preserve_zoom),
    )
