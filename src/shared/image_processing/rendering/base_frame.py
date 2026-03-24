from typing import TYPE_CHECKING, Optional

from PIL import Image

from plugins.analysis.processing import (
    create_edge_map,
    create_grayscale_diff,
    create_highlight_diff,
    create_ssim_map,
    extract_channel,
)

if TYPE_CHECKING:
    from shared.image_processing.pipeline import RenderContext

def get_resize_filter(method: str) -> Image.Resampling:
    mapping = {
        "NEAREST": Image.Resampling.NEAREST,
        "BILINEAR": Image.Resampling.BILINEAR,
        "BICUBIC": Image.Resampling.BICUBIC,
        "LANCZOS": Image.Resampling.LANCZOS,
        "EWA_LANCZOS": Image.Resampling.LANCZOS,
    }
    return mapping.get(method.upper(), Image.Resampling.BILINEAR)

def resolve_render_images(
    ctx: "RenderContext",
) -> tuple[Image.Image | None, Image.Image | None]:
    img1_scaled = ctx.image1
    img2_scaled = ctx.image2
    if not img1_scaled and not img2_scaled:
        return None, None
    target_size = img1_scaled.size if img1_scaled else img2_scaled.size
    if not img1_scaled:
        img1_scaled = Image.new("RGBA", target_size, (0, 0, 0, 0))
    if not img2_scaled:
        img2_scaled = Image.new("RGBA", target_size, (0, 0, 0, 0))
    if img1_scaled.size != img2_scaled.size:
        if img1_scaled.size == target_size:
            img2_scaled = img2_scaled.resize(target_size, Image.Resampling.NEAREST)
        else:
            img1_scaled = img1_scaled.resize(target_size, Image.Resampling.NEAREST)
    return img1_scaled, img2_scaled

def create_final_canvas(base_image: Image.Image, geometry) -> Image.Image:
    final_canvas = Image.new(
        "RGBA",
        (geometry.canvas_w, geometry.canvas_h),
        (0, 0, 0, 0),
    )
    final_canvas.paste(base_image, (geometry.padding_left, geometry.padding_top))
    return final_canvas

def get_or_create_base_image(
    ctx: "RenderContext",
    img1_scaled: Image.Image,
    img2_scaled: Image.Image,
    font_path: Optional[str],
) -> Optional[Image.Image]:
    base_image = None
    current_bg_key = (
        id(img1_scaled),
        id(img2_scaled),
        ctx.split_pos,
        ctx.is_horizontal,
        ctx.diff_mode,
        ctx.channel_view_mode,
        ctx.divider_line_visible,
        ctx.divider_line_thickness,
        (
            tuple(ctx.divider_line_color)
            if isinstance(ctx.divider_line_color, (list, tuple))
            else ctx.divider_line_color
        ),
    )
    if ctx.background_cache_dict is not None:
        if ctx.background_cache_dict.get("last_key") == current_bg_key:
            base_image = ctx.background_cache_dict.get("image")
    if base_image is None:
        base_image = create_base_image(ctx, img1_scaled, img2_scaled, font_path)
        if ctx.background_cache_dict is not None and base_image:
            ctx.background_cache_dict["last_key"] = current_bg_key
            ctx.background_cache_dict["image"] = base_image
    return base_image

def create_base_image(
    ctx: "RenderContext",
    img1: Image.Image,
    img2: Image.Image,
    font_path: Optional[str],
) -> Optional[Image.Image]:
    if ctx.channel_view_mode != "RGB":
        img1 = extract_channel(img1, ctx.channel_view_mode) or img1
        img2 = extract_channel(img2, ctx.channel_view_mode) or img2
    if ctx.diff_mode != "off":
        return apply_diff_mode(ctx, img1, img2, font_path)
    return create_split_image(ctx, img1, img2)

def apply_diff_mode(
    ctx: "RenderContext", img1: Image.Image, img2: Image.Image, font_path: Optional[str]
) -> Optional[Image.Image]:
    if ctx.diff_mode == "edges":
        edge_map1 = create_edge_map(img1) or img1
        edge_map2 = create_edge_map(img2) or img2
        return create_split_image(ctx, edge_map1, edge_map2)
    if ctx.diff_mode == "highlight":
        return create_highlight_diff(img1, img2, threshold=10, font_path=font_path)
    if ctx.diff_mode == "grayscale":
        return create_grayscale_diff(img1, img2, font_path=font_path)
    if ctx.diff_mode == "ssim":
        return create_ssim_map(img1, img2, font_path=font_path)
    return create_split_image(ctx, img1, img2)

def create_split_image(
    ctx: "RenderContext", img1: Image.Image, img2: Image.Image
) -> Optional[Image.Image]:
    if img1.size != img2.size:
        min_w = min(img1.width, img2.width)
        min_h = min(img1.height, img2.height)
        if min_w <= 0 or min_h <= 0:
            return None
        img1 = img1.resize((min_w, min_h), Image.Resampling.BILINEAR)
        img2 = img2.resize((min_w, min_h), Image.Resampling.BILINEAR)
    width, height = img1.size
    result = Image.new("RGBA", (width, height))
    if not ctx.is_horizontal:
        split_pos = int(round(width * ctx.split_pos))
        if split_pos > 0:
            result.paste(img1.crop((0, 0, split_pos, height)), (0, 0))
        if split_pos < width:
            result.paste(img2.crop((split_pos, 0, width, height)), (split_pos, 0))
    else:
        split_pos = int(round(height * ctx.split_pos))
        if split_pos > 0:
            result.paste(img1.crop((0, 0, width, split_pos)), (0, 0))
        if split_pos < height:
            result.paste(img2.crop((0, split_pos, width, height)), (0, split_pos))
    return result

