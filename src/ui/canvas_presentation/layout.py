from __future__ import annotations

from .models import CanvasContentLayout, CanvasTarget

def compute_content_layout(
    target: CanvasTarget,
    *,
    image_width: int,
    image_height: int,
) -> CanvasContentLayout:
    if image_width <= 0 or image_height <= 0:
        return CanvasContentLayout(
            canvas_width=max(1, target.width),
            canvas_height=max(1, target.height),
            content_x=0,
            content_y=0,
            content_width=0,
            content_height=0,
        )

    canvas_w = max(1, target.width)
    canvas_h = max(1, target.height)
    if target.fit_mode == "stretch":
        content_w = canvas_w
        content_h = canvas_h
    else:
        ratio = min(canvas_w / image_width, canvas_h / image_height)
        content_w = max(1, int(image_width * ratio))
        content_h = max(1, int(image_height * ratio))

    return CanvasContentLayout(
        canvas_width=canvas_w,
        canvas_height=canvas_h,
        content_x=(canvas_w - content_w) // 2,
        content_y=(canvas_h - content_h) // 2,
        content_width=content_w,
        content_height=content_h,
    )
