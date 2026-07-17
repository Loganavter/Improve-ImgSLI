from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class QuickContentRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def resolve_axis_position(offset: float, size: float, fraction: float) -> float:
    """Where a normalized ``fraction`` along one axis of a rect sits in
    absolute units. The one primitive every split-position/divider screen
    mapping is built from — see
    docs/dev/QRHI_CANVAS_FEATURES.md."""
    return float(offset) + float(size) * float(fraction)


def map_content_rect_through_view(
    content_rect: tuple[float, float, float, float],
    *,
    widget_width: float,
    widget_height: float,
    zoom_level: float,
    pan_offset_x: float,
    pan_offset_y: float,
) -> tuple[float, float, float, float]:
    """Map a fit-zoom letterbox rect through the same camera as ``base.frag``.

    ``content_rect_px`` is authored at identity camera (zoom=1, pan=0). The
    base image then applies ``screen = (uv - 0.5 + pan) * zoom + 0.5``. Divider
    scissor must use that transformed rect — otherwise a vertical spit line
    tracks on X via ``display_split`` but its Y extent stays glued to the
    unzoomed letterbox and detaches from the pictures when panning/zooming.
    """
    cx, cy, cw, ch = (float(v) for v in content_rect)
    width = max(1.0, float(widget_width))
    height = max(1.0, float(widget_height))
    zoom = max(float(zoom_level), 1e-6)
    pan_x = float(pan_offset_x)
    pan_y = float(pan_offset_y)

    def _map_axis(value: float, size: float, pan: float) -> float:
        return ((value / size) - 0.5 + pan) * zoom + 0.5

    x0 = _map_axis(cx, width, pan_x) * width
    x1 = _map_axis(cx + cw, width, pan_x) * width
    y0 = _map_axis(cy, height, pan_y) * height
    y1 = _map_axis(cy + ch, height, pan_y) * height
    left = min(x0, x1)
    top = min(y0, y1)
    return (left, top, abs(x1 - x0), abs(y1 - y0))
