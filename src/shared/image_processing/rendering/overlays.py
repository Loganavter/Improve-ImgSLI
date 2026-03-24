from typing import TYPE_CHECKING

from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QRect

from .geometry import clamp_capture_position

if TYPE_CHECKING:
    from shared.image_processing.pipeline import RenderContext

def draw_divider_line_on_canvas(
    ctx: "RenderContext",
    canvas: Image.Image,
    padding_left: int,
    padding_top: int,
    img_w: int,
    img_h: int,
):
    draw = ImageDraw.Draw(canvas)
    clip_rect = ctx.divider_clip_rect
    if not ctx.is_horizontal:
        x = padding_left + int(round(img_w * ctx.split_pos))
        y0 = padding_top
        y1 = padding_top + img_h - 1
        if clip_rect:
            _clip_x, clip_y, _clip_w, clip_h = clip_rect
            y0 = clip_y
            y1 = clip_y + clip_h - 1
        draw.rectangle(
            [
                x - ctx.divider_line_thickness // 2,
                y0,
                x + (ctx.divider_line_thickness + 1) // 2 - 1,
                y1,
            ],
            fill=ctx.divider_line_color,
        )
        return
    y = padding_top + int(round(img_h * ctx.split_pos))
    x0 = padding_left
    x1 = padding_left + img_w - 1
    if clip_rect:
        clip_x, _clip_y, clip_w, _clip_h = clip_rect
        x0 = clip_x
        x1 = clip_x + clip_w - 1
    draw.rectangle(
        [
            x0,
            y - ctx.divider_line_thickness // 2,
            x1,
            y + (ctx.divider_line_thickness + 1) // 2 - 1,
        ],
        fill=ctx.divider_line_color,
    )

def draw_capture_area_if_needed(pipeline, ctx: "RenderContext", final_canvas: Image.Image, geometry, is_separated_layers: bool):
    if not (ctx.use_magnifier and ctx.show_capture_area and not is_separated_layers):
        return
    ref_dim = min(geometry.img_w, geometry.img_h)
    cap_size = max(5, int(round(ctx.capture_size * ref_dim)))
    clamped_x, clamped_y = clamp_capture_position(
        ctx.magnifier_pos.x(),
        ctx.magnifier_pos.y(),
        geometry.img_w,
        geometry.img_h,
        ctx.capture_size,
    )
    cap_x = geometry.padding_left + int(round(clamped_x * geometry.img_w))
    cap_y = geometry.padding_top + int(round(clamped_y * geometry.img_h))
    capture_color = pipeline._get_highlighted_color(
        ctx.capture_ring_color,
        ctx.highlighted_magnifier_element == "capture",
    )
    pipeline.magnifier_drawer.draw_capture_area(
        final_canvas, QPoint(cap_x, cap_y), cap_size, color=capture_color
    )

def render_divider_patch(ctx: "RenderContext", img_rect: QRect):
    if (
        not ctx.divider_line_visible
        or ctx.divider_line_thickness <= 0
        or ctx.diff_mode != "off"
    ):
        return None, QPoint(0, 0)
    try:
        img_w = img_rect.width()
        img_h = img_rect.height()
        thickness = ctx.divider_line_thickness
        clip_rect = ctx.divider_clip_rect
        if not ctx.is_horizontal:
            x = int(round(img_w * ctx.split_pos))
            patch_x = max(0, x - thickness - 2)
            patch_w = min(thickness + 4, img_w - patch_x)
            patch_y = 0
            patch_h = img_h
            if clip_rect:
                _clip_x, clip_y, _clip_w, clip_h = clip_rect
                patch_y = max(0, clip_y)
                patch_h = min(clip_h, img_h - patch_y)
            patch_canvas = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(patch_canvas)
            local_x = x - patch_x
            draw.rectangle(
                [local_x - thickness // 2, 0, local_x + (thickness + 1) // 2 - 1, patch_h - 1],
                fill=ctx.divider_line_color,
            )
            return patch_canvas, QPoint(patch_x, patch_y)
        y = int(round(img_h * ctx.split_pos))
        patch_y = max(0, y - thickness - 2)
        patch_x = 0
        patch_w = img_w
        patch_h = min(thickness + 4, img_h - patch_y)
        if clip_rect:
            clip_x, _clip_y, clip_w, _clip_h = clip_rect
            patch_x = max(0, clip_x)
            patch_w = min(clip_w, img_w - patch_x)
        patch_canvas = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(patch_canvas)
        local_y = y - patch_y
        draw.rectangle(
            [0, local_y - thickness // 2, patch_w - 1, local_y + (thickness + 1) // 2 - 1],
            fill=ctx.divider_line_color,
        )
        return patch_canvas, QPoint(patch_x, patch_y)
    except Exception:
        return None, QPoint(0, 0)
