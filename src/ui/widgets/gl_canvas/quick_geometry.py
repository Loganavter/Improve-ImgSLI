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

def compute_display_split_position(
    *,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
    split_visual: float,
    is_horizontal: bool,
    zoom_level: float,
    pan_offset_x: float,
    pan_offset_y: float,
) -> float:
    content_rect = build_content_rect(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=image_width,
        image_height=image_height,
    )
    if content_rect is None:
        return max(0.0, min(1.0, float(split_visual)))

    if is_horizontal:
        base = (content_rect.y + (content_rect.height * split_visual)) / max(1.0, float(widget_height))
        pan = pan_offset_y
    else:
        base = (content_rect.x + (content_rect.width * split_visual)) / max(1.0, float(widget_width))
        pan = pan_offset_x

    return max(0.0, min(1.0, (base - 0.5 + pan) * zoom_level + 0.5))

def map_screen_to_image_rel(
    *,
    cursor_x: float,
    cursor_y: float,
    widget_width: int,
    widget_height: int,
    image_width: int,
    image_height: int,
    zoom_level: float,
    pan_offset_x: float,
    pan_offset_y: float,
) -> tuple[float | None, float | None]:
    content_rect = build_content_rect(
        widget_width=widget_width,
        widget_height=widget_height,
        image_width=image_width,
        image_height=image_height,
    )
    if content_rect is None:
        return None, None

    width = max(1.0, float(widget_width))
    height = max(1.0, float(widget_height))
    screen_norm_x = float(cursor_x) / width
    screen_norm_y = float(cursor_y) / height
    local_norm_x = (screen_norm_x - 0.5) / max(zoom_level, 1e-6) + 0.5 - pan_offset_x
    local_norm_y = (screen_norm_y - 0.5) / max(zoom_level, 1e-6) + 0.5 - pan_offset_y
    local_x = local_norm_x * width
    local_y = local_norm_y * height

    clamped_x = max(content_rect.x, min(local_x, content_rect.right))
    clamped_y = max(content_rect.y, min(local_y, content_rect.bottom))
    image_rel_x = (clamped_x - content_rect.x) / max(content_rect.width, 1.0)
    image_rel_y = (clamped_y - content_rect.y) / max(content_rect.height, 1.0)
    return image_rel_x, image_rel_y
