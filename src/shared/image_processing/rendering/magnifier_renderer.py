import logging
import math
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QRect

from core.store import Store
from .geometry import clamp_capture_position
from .base_frame import get_resize_filter

if TYPE_CHECKING:
    from shared.image_processing.pipeline import RenderContext

logger = logging.getLogger("ImproveImgSLI")

def is_effective_magnifier_interactive(ctx: "RenderContext") -> bool:
    return bool(
        getattr(ctx, "is_interactive_mode", False)
        and getattr(ctx, "optimize_magnifier_movement", True)
    )

def render_magnifier_if_needed(
    pipeline,
    ctx: "RenderContext",
    final_canvas: Image.Image,
    img1_scaled: Image.Image,
    img2_scaled: Image.Image,
    geometry,
    is_separated_layers: bool,
):
    if not (ctx.use_magnifier and ctx.magnifier_drawing_coords):
        return None, None
    if is_separated_layers:
        magnifier_pil, _ = render_magnifier_patch(pipeline, ctx)
        combined_center_point = (
            ctx.magnifier_drawing_coords[2]
            if len(ctx.magnifier_drawing_coords) > 2
            else None
        )
        return magnifier_pil, combined_center_point
    combined_center_point = draw_magnifier_full(
        pipeline,
        ctx,
        final_canvas,
        img1_scaled,
        img2_scaled,
        geometry.padding_left,
        geometry.padding_top,
        geometry.img_w,
        geometry.img_h,
    )
    return None, combined_center_point

def _build_temp_store(ctx: "RenderContext") -> Store:
    temp_store = Store()
    temp_store.viewport.view_state.magnifier_visible_left = ctx.magnifier_visible_left
    temp_store.viewport.view_state.magnifier_visible_center = ctx.magnifier_visible_center
    temp_store.viewport.view_state.magnifier_visible_right = ctx.magnifier_visible_right
    temp_store.viewport.view_state.magnifier_is_horizontal = ctx.magnifier_is_horizontal
    temp_store.viewport.view_state.diff_mode = ctx.diff_mode
    return temp_store

def _resolve_magnifier_interpolation(pipeline, ctx: "RenderContext") -> str:
    magnifier_interpolation = ctx.interpolation_method
    effective_interactive = is_effective_magnifier_interactive(ctx)
    if effective_interactive and ctx.magnifier_movement_interpolation_method:
        magnifier_interpolation = ctx.magnifier_movement_interpolation_method
    return magnifier_interpolation

def draw_magnifier_full(
    pipeline,
    ctx: "RenderContext",
    canvas: Image.Image,
    img1_scaled: Image.Image,
    img2_scaled: Image.Image,
    padding_left: int,
    padding_top: int,
    img_w: int,
    img_h: int,
):
    if not ctx.magnifier_drawing_coords or ctx.magnifier_drawing_coords[2] is None:
        return None
    combined_center_point = None
    mag_mid_on_canvas = QPoint(
        ctx.magnifier_drawing_coords[2].x() + padding_left,
        ctx.magnifier_drawing_coords[2].y() + padding_top,
    )
    if ctx.show_magnifier_guides and not getattr(ctx, "return_layers", False):
        draw_magnifier_guides(
            pipeline, ctx, canvas, mag_mid_on_canvas, padding_left, padding_top, img_w, img_h
        )
    original_img1 = ctx.original_image1 or img1_scaled
    original_img2 = ctx.original_image2 or img2_scaled
    temp_store = _build_temp_store(ctx)
    interactive_center_local = pipeline.magnifier_drawer.draw_magnifier(
        temp_store,
        canvas,
        original_img1,
        original_img2,
        ctx.magnifier_drawing_coords[0],
        ctx.magnifier_drawing_coords[1],
        mag_mid_on_canvas,
        ctx.magnifier_drawing_coords[3],
        ctx.magnifier_drawing_coords[4],
        _resolve_magnifier_interpolation(pipeline, ctx),
        ctx.is_horizontal,
        ctx.is_magnifier_combined,
        is_interactive_render=is_effective_magnifier_interactive(ctx),
        internal_split=ctx.magnifier_internal_split,
        divider_visible=ctx.magnifier_divider_visible,
        divider_color=ctx.magnifier_divider_color,
        divider_thickness=ctx.magnifier_divider_thickness,
        border_color=pipeline._get_highlighted_color(
            ctx.magnifier_border_color, ctx.highlighted_magnifier_element == "border"
        ),
        capture_ring_color=ctx.capture_ring_color,
        font_path=pipeline.font_path,
        external_cache=ctx.magnifier_cache_dict,
    )
    if interactive_center_local:
        combined_center_point = QPoint(
            interactive_center_local.x() - padding_left,
            interactive_center_local.y() - padding_top,
        )
    return combined_center_point

def render_magnifier_patch(pipeline, ctx: "RenderContext"):
    if not ctx.use_magnifier or not ctx.magnifier_drawing_coords:
        return None, QPoint(0, 0)
    try:
        coords = ctx.magnifier_drawing_coords
        magnifier_bbox = coords[5] if len(coords) > 5 else None
        if not magnifier_bbox or not isinstance(magnifier_bbox, QRect) or magnifier_bbox.isEmpty():
            return None, QPoint(0, 0)
        patch_w = magnifier_bbox.width()
        patch_h = magnifier_bbox.height()
        patch_canvas = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
        local_center = QPoint(patch_w // 2, patch_h // 2)
        temp_store = _build_temp_store(ctx)
        original_img1 = ctx.original_image1 or ctx.image1
        original_img2 = ctx.original_image2 or ctx.image2
        pipeline.magnifier_drawer.draw_magnifier(
            temp_store,
            patch_canvas,
            original_img1,
            original_img2,
            coords[0],
            coords[1],
            local_center,
            coords[3],
            coords[4],
            _resolve_magnifier_interpolation(pipeline, ctx),
            ctx.is_horizontal,
            ctx.is_magnifier_combined,
            is_interactive_render=is_effective_magnifier_interactive(ctx),
            internal_split=ctx.magnifier_internal_split,
            divider_visible=ctx.magnifier_divider_visible,
            divider_color=ctx.magnifier_divider_color,
            divider_thickness=ctx.magnifier_divider_thickness,
            border_color=pipeline._get_highlighted_color(
                ctx.magnifier_border_color, ctx.highlighted_magnifier_element == "border"
            ),
            capture_ring_color=ctx.capture_ring_color,
            font_path=pipeline.font_path,
            external_cache=ctx.magnifier_cache_dict,
        )
        return patch_canvas, magnifier_bbox.topLeft()
    except Exception as e:
        logger.error(f"Error rendering magnifier patch: {e}", exc_info=True)
        return None, QPoint(0, 0)

def render_guides_patch(pipeline, ctx: "RenderContext", img_rect: QRect, padding_left: int, padding_top: int):
    if not ctx.use_magnifier or not ctx.show_magnifier_guides or ctx.magnifier_guides_thickness == 0:
        return None, QPoint(0, 0)
    if not ctx.magnifier_drawing_coords or not ctx.magnifier_drawing_coords[2]:
        return None, QPoint(0, 0)
    try:
        img_w = img_rect.width()
        img_h = img_rect.height()
        canvas_w = img_rect.width() + padding_left * 2
        canvas_h = img_rect.height() + padding_top * 2
        patch_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        mag_mid_on_canvas = QPoint(
            ctx.magnifier_drawing_coords[2].x() + padding_left,
            ctx.magnifier_drawing_coords[2].y() + padding_top,
        )
        draw_magnifier_guides(
            pipeline, ctx, patch_canvas, mag_mid_on_canvas, padding_left, padding_top, img_w, img_h
        )
        return patch_canvas, QPoint(0, 0)
    except Exception as e:
        logger.error(f"Error rendering guides patch: {e}", exc_info=True)
        return None, QPoint(0, 0)

def render_capture_area_patch(pipeline, ctx: "RenderContext", img_rect: QRect, padding_left: int, padding_top: int):
    if not ctx.use_magnifier or not ctx.show_capture_area:
        return None, QPoint(0, 0)
    try:
        img_w = img_rect.width()
        img_h = img_rect.height()
        ref_dim = min(img_w, img_h)
        cap_size = max(5, int(round(ctx.capture_size * ref_dim)))
        clamped_x, clamped_y = clamp_capture_position(
            ctx.magnifier_pos.x(), ctx.magnifier_pos.y(), img_w, img_h, ctx.capture_size
        )
        cap_x = int(round(clamped_x * img_w))
        cap_y = int(round(clamped_y * img_h))
        margin = cap_size + 20
        patch_x = max(0, cap_x - margin)
        patch_y = max(0, cap_y - margin)
        patch_w = min(margin * 2, img_w - patch_x)
        patch_h = min(margin * 2, img_h - patch_y)
        patch_canvas = Image.new("RGBA", (patch_w, patch_h), (0, 0, 0, 0))
        local_cap_x = cap_x - patch_x
        local_cap_y = cap_y - patch_y
        capture_color = pipeline._get_highlighted_color(
            ctx.capture_ring_color, ctx.highlighted_magnifier_element == "capture"
        )
        pipeline.magnifier_drawer.draw_capture_area(
            patch_canvas, QPoint(local_cap_x, local_cap_y), cap_size, color=capture_color
        )
        return patch_canvas, QPoint(patch_x + padding_left, patch_y + padding_top)
    except Exception as e:
        logger.error(f"Error rendering capture area patch: {e}", exc_info=True)
        return None, QPoint(0, 0)

def draw_magnifier_guides(
    pipeline,
    ctx: "RenderContext",
    canvas: Image.Image,
    mag_mid_on_canvas: QPoint,
    padding_left: int,
    padding_top: int,
    img_w: int,
    img_h: int,
):
    if ctx.magnifier_guides_thickness == 0 or not ctx.show_magnifier_guides:
        return
    laser_centers = []
    mid_x, mid_y = mag_mid_on_canvas.x(), mag_mid_on_canvas.y()
    mag_size = ctx.magnifier_drawing_coords[3]
    spacing = ctx.magnifier_drawing_coords[4]
    is_visual_diff = ctx.diff_mode in ("highlight", "grayscale", "ssim", "edges")
    if ctx.is_magnifier_combined:
        laser_centers.append(mag_mid_on_canvas)
        if is_visual_diff:
            if not ctx.is_horizontal:
                laser_centers.append(QPoint(mid_x, int(round(mid_y + mag_size + 8))))
            else:
                laser_centers.append(QPoint(int(round(mid_x + mag_size + 8)), mid_y))
    else:
        if is_visual_diff:
            spacing_f = float(spacing)
            offset = max(mag_size, mag_size + spacing_f)
            if not ctx.is_horizontal:
                if ctx.magnifier_visible_left:
                    laser_centers.append(QPoint(int(round(mid_x - offset)), int(round(mid_y))))
                if ctx.magnifier_visible_center:
                    laser_centers.append(mag_mid_on_canvas)
                if ctx.magnifier_visible_right:
                    laser_centers.append(QPoint(int(round(mid_x + offset)), int(round(mid_y))))
            else:
                if ctx.magnifier_visible_left:
                    laser_centers.append(QPoint(int(round(mid_x)), int(round(mid_y - offset))))
                if ctx.magnifier_visible_center:
                    laser_centers.append(mag_mid_on_canvas)
                if ctx.magnifier_visible_right:
                    laser_centers.append(QPoint(int(round(mid_x)), int(round(mid_y + offset))))
        else:
            radius = mag_size / 2.0
            offset = radius + (spacing / 2.0)
            if not ctx.magnifier_is_horizontal:
                if ctx.magnifier_visible_left:
                    laser_centers.append(QPoint(int(mid_x - offset), mid_y))
                if ctx.magnifier_visible_right:
                    laser_centers.append(QPoint(int(mid_x + offset), mid_y))
            else:
                if ctx.magnifier_visible_left:
                    laser_centers.append(QPoint(mid_x, int(mid_y - offset)))
                if ctx.magnifier_visible_right:
                    laser_centers.append(QPoint(mid_x, int(mid_y + offset)))
    ref_dim = min(img_w, img_h)
    r_mag = mag_size / 2.0
    r_cap = max(5, int(round(ctx.capture_size * ref_dim))) / 2.0
    clamped_x, clamped_y = clamp_capture_position(
        ctx.magnifier_pos.x(), ctx.magnifier_pos.y(), img_w, img_h, ctx.capture_size
    )
    cap_x = padding_left + int(round(clamped_x * img_w))
    cap_y = padding_top + int(round(clamped_y * img_h))
    p_cap = QPoint(cap_x, cap_y)
    laser_color = pipeline._get_highlighted_color(
        ctx.magnifier_laser_color, ctx.highlighted_magnifier_element == "laser"
    )
    is_interactive = ctx.is_interactive_mode
    optimize_smoothing = ctx.optimize_laser_smoothing
    if is_interactive:
        if optimize_smoothing:
            interpolation_method = ctx.laser_smoothing_interpolation_method
            should_smooth = True
        else:
            interpolation_method = "LANCZOS"
            should_smooth = False
    else:
        interpolation_method = "LANCZOS"
        should_smooth = True
    for p_mag in laser_centers:
        if p_mag:
            draw_aa_laser(
                canvas,
                p_mag,
                p_cap,
                r_mag,
                r_cap,
                laser_color,
                not should_smooth,
                ctx.magnifier_guides_thickness,
                interpolation_method,
            )

def draw_aa_laser(
    canvas: Image.Image,
    p1: QPoint,
    p2: QPoint,
    r1: float,
    r2: float,
    color,
    is_interactive: bool,
    thickness: int = 1,
    interpolation_method: str = "BILINEAR",
):
    line_width = max(1, int(round(thickness)))
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    dist = math.hypot(dx, dy)
    if dist <= (r1 + r2):
        return
    nx, ny = dx / dist, dy / dist
    ax, ay = p1.x() + nx * r1, p1.y() + ny * r1
    bx, by = p2.x() - nx * r2, p2.y() - ny * r2
    if is_interactive:
        draw = ImageDraw.Draw(canvas)
        opaque_color = (*color[:3], 255)
        draw.line([(ax, ay), (bx, by)], fill=opaque_color, width=line_width)
        return
    scale = 4
    padding = 4
    left = int(min(ax, bx)) - padding
    top = int(min(ay, by)) - padding
    right = int(max(ax, bx)) + padding
    bottom = int(max(ay, by)) + padding
    bbox_w = right - left
    bbox_h = bottom - top
    if bbox_w <= 0 or bbox_h <= 0:
        return
    hr_canvas = Image.new("RGBA", (bbox_w * scale, bbox_h * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hr_canvas)
    hr_ax = (ax - left) * scale
    hr_ay = (ay - top) * scale
    hr_bx = (bx - left) * scale
    hr_by = (by - top) * scale
    opaque_color = (*color[:3], 255)
    draw.line(
        [(hr_ax, hr_ay), (hr_bx, hr_by)],
        fill=opaque_color,
        width=max(1, int(round(line_width * scale))),
    )
    smooth_line = hr_canvas.resize((bbox_w, bbox_h), get_resize_filter(interpolation_method))
    canvas.alpha_composite(smooth_line, (left, top))
