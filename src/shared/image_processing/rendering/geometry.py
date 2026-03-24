from typing import TYPE_CHECKING

from .models import CanvasGeometry

if TYPE_CHECKING:
    from shared.image_processing.pipeline import RenderContext
    from PIL import Image

from core.constants import AppConstants

def resolve_interpolation(main_method: str, opt_method: str) -> str:
    main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_method, 999)
    opt_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(opt_method, 999)
    return main_method if main_speed <= opt_speed else opt_method

def clamp_capture_position(
    rel_pos_x: float,
    rel_pos_y: float,
    canvas_width: int,
    canvas_height: int,
    capture_size_relative: float,
):
    if canvas_width <= 0 or canvas_height <= 0:
        return rel_pos_x, rel_pos_y
    unified_ref_dim = min(canvas_width, canvas_height)
    capture_size_on_unified = capture_size_relative * unified_ref_dim
    radius_rel_x = (
        (capture_size_on_unified / 2.0) / canvas_width if canvas_width > 0 else 0.0
    )
    radius_rel_y = (
        (capture_size_on_unified / 2.0) / canvas_height if canvas_height > 0 else 0.0
    )
    eff_rel_x = max(radius_rel_x, min(rel_pos_x, 1.0 - radius_rel_x))
    eff_rel_y = max(radius_rel_y, min(rel_pos_y, 1.0 - radius_rel_y))
    return eff_rel_x, eff_rel_y

def compute_canvas_geometry(ctx: "RenderContext", image: "Image.Image") -> CanvasGeometry:
    img_w, img_h = image.size
    padding_left = 0
    padding_top = 0
    canvas_w = img_w
    canvas_h = img_h
    magnifier_bbox_on_canvas = None

    if ctx.use_magnifier and ctx.magnifier_drawing_coords:
        magnifier_bbox = (
            ctx.magnifier_drawing_coords[5]
            if len(ctx.magnifier_drawing_coords) > 5
            else None
        )
        if magnifier_bbox and magnifier_bbox.isValid():
            padding_left = abs(min(0, magnifier_bbox.left()))
            padding_top = abs(min(0, magnifier_bbox.top()))
            padding_right = max(0, magnifier_bbox.right() - img_w)
            padding_bottom = max(0, magnifier_bbox.bottom() - img_h)
            canvas_w = img_w + padding_left + padding_right
            canvas_h = img_h + padding_top + padding_bottom
            magnifier_bbox_on_canvas = magnifier_bbox.translated(
                padding_left, padding_top
            )

    return CanvasGeometry(
        img_w=img_w,
        img_h=img_h,
        padding_left=padding_left,
        padding_top=padding_top,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        magnifier_bbox_on_canvas=magnifier_bbox_on_canvas,
    )

