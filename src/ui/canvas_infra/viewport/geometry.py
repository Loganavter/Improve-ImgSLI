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

def build_content_rect(
    *,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
) -> QuickContentRect | None:
    if widget_width <= 0 or widget_height <= 0 or image_width <= 0 or image_height <= 0:
        return None

    ratio = min(widget_width / image_width, widget_height / image_height)
    content_width = max(1.0, image_width * ratio)
    content_height = max(1.0, image_height * ratio)
    return QuickContentRect(
        x=(widget_width - content_width) / 2.0,
        y=(widget_height - content_height) / 2.0,
        width=content_width,
        height=content_height,
    )
