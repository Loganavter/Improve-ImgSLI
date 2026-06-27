from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RELATIVE_REFERENCE_SHORT_EDGE_PX = 1000.0


@dataclass(frozen=True, slots=True)
class RenderMetrics:
    canvas_to_view: float
    view_to_screen: float
    output_scale: float
    content_width: float
    content_height: float
    mode: Literal["interactive", "preview", "export"]


def relative_short_edge_scale(
    short_edge_px: float,
    *,
    output_scale: float = 1.0,
) -> float:
    short_edge = max(0.0, float(short_edge_px))
    if short_edge <= 0.0:
        return max(0.0, float(output_scale))
    return (short_edge / RELATIVE_REFERENCE_SHORT_EDGE_PX) * max(
        0.0, float(output_scale)
    )


def resolve_relative_px(
    value: float,
    *,
    short_edge_px: float,
    output_scale: float = 1.0,
) -> float:
    return max(0.0, float(value)) * relative_short_edge_scale(
        short_edge_px,
        output_scale=output_scale,
    )


def resolve_image_px(value: float, metrics: RenderMetrics) -> float:
    return max(0.0, float(value)) * max(0.0, float(metrics.canvas_to_view))


def resolve_view_px(value: float, metrics: RenderMetrics) -> float:
    short_edge = min(
        max(0.0, float(metrics.content_width)),
        max(0.0, float(metrics.content_height)),
    )
    return resolve_relative_px(
        value,
        short_edge_px=short_edge,
        output_scale=metrics.output_scale,
    )


def resolve_screen_px(value: float, metrics: RenderMetrics) -> float:
    return max(0.0, float(value))


def resolve_font_px(base_px: float, metrics: RenderMetrics) -> int:
    return max(1, int(round(resolve_view_px(base_px, metrics))))
