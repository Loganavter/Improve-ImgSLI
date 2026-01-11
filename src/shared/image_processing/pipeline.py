

import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QPointF, QRect

from core.constants import AppConstants
from plugins.analysis.processing import (
    create_highlight_diff,
    create_grayscale_diff,
    create_ssim_map,
    create_edge_map,
    extract_channel
)
from shared.image_processing.drawing.magnifier_drawer import (
    MIN_CAPTURE_THICKNESS,
    MagnifierDrawer,
)
from shared.image_processing.drawing.text_drawer import TextDrawer

logger = logging.getLogger("ImproveImgSLI")

_global_text_drawer = None
_global_text_drawer_font_path = None
_global_magnifier_drawer = None

def _get_global_text_drawer(font_path: Optional[str] = None) -> TextDrawer:
    global _global_text_drawer, _global_text_drawer_font_path

    font_path_str = font_path if font_path else ""

    if _global_text_drawer is None or _global_text_drawer_font_path != font_path_str:
        _global_text_drawer = TextDrawer(font_path_str)
        _global_text_drawer_font_path = font_path_str

    return _global_text_drawer

def _get_global_magnifier_drawer() -> MagnifierDrawer:
    global _global_magnifier_drawer

    if _global_magnifier_drawer is None:
        _global_magnifier_drawer = MagnifierDrawer()

    return _global_magnifier_drawer

def _resolve_interpolation(main_method: str, opt_method: str) -> str:
    from core.constants import AppConstants
    main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_method, 999)
    opt_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(opt_method, 999)

    if main_speed <= opt_speed:
        return main_method
    return opt_method

def _clamp_capture_position(rel_pos_x: float, rel_pos_y: float, canvas_width: int, canvas_height: int, capture_size_relative: float) -> Tuple[float, float]:
    if canvas_width <= 0 or canvas_height <= 0:
        return rel_pos_x, rel_pos_y

    unified_ref_dim = min(canvas_width, canvas_height)
    capture_size_on_unified = capture_size_relative * unified_ref_dim

    radius_rel_x = (capture_size_on_unified / 2.0) / canvas_width if canvas_width > 0 else 0.0
    radius_rel_y = (capture_size_on_unified / 2.0) / canvas_height if canvas_height > 0 else 0.0

    eff_rel_x = max(radius_rel_x, min(rel_pos_x, 1.0 - radius_rel_x))
    eff_rel_y = max(radius_rel_y, min(rel_pos_y, 1.0 - radius_rel_y))

    return eff_rel_x, eff_rel_y

@dataclass
class RenderContext:
    width: int
    height: int
    image1: Image.Image
    image2: Image.Image
    split_pos: float
    magnifier_pos: QPoint
    diff_mode: str
    magnifier_offset: Optional[QPoint] = None
    channel_view_mode: str = "RGB"
    is_horizontal: bool = False
    use_magnifier: bool = False
    magnifier_size: float = 0.2
    capture_size: float = 0.1
    show_capture_area: bool = True
    divider_line_visible: bool = True
    divider_line_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    divider_line_thickness: int = 3
    include_file_names: bool = False
    file_name1: str = ""
    file_name2: str = ""
    magnifier_is_horizontal: bool = False
    magnifier_divider_visible: bool = True
    magnifier_divider_color: Tuple[int, int, int, int] = (255, 255, 255, 230)
    magnifier_divider_thickness: int = 2
    magnifier_internal_split: float = 0.5
    interpolation_method: str = "BILINEAR"

    original_image1: Optional[Image.Image] = None
    original_image2: Optional[Image.Image] = None

    magnifier_drawing_coords: Optional[Tuple] = None

    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    is_magnifier_combined: bool = False
    magnifier_border_color: Tuple[int, int, int, int] = (255, 255, 255, 230)
    magnifier_laser_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    capture_ring_color: Tuple[int, int, int, int] = (255, 50, 100, 230)
    show_magnifier_guides: bool = False
    magnifier_guides_thickness: int = 1
    is_interactive_mode: bool = False
    optimize_laser_smoothing: bool = False
    movement_interpolation_method: str = "BILINEAR"
    magnifier_movement_interpolation_method: str = "BILINEAR"
    laser_smoothing_interpolation_method: str = "BILINEAR"
    magnifier_offset_relative_visual: Optional[QPoint] = None
    magnifier_spacing_relative_visual: float = 0.05
    highlighted_magnifier_element: Optional[str] = None

    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: Tuple[int, int, int, int] = (255, 0, 0, 255)
    file_name_bg_color: Tuple[int, int, int, int] = (0, 0, 0, 80)
    draw_text_background: bool = True
    text_placement_mode: str = "edges"
    max_name_length: int = 50

    magnifier_cache_dict: dict = None
    background_cache_dict: dict = None

class RenderingPipeline:

    def __init__(self, font_path: Optional[str] = None):
        self.font_path = font_path

        self.text_drawer = _get_global_text_drawer(font_path)
        self.magnifier_drawer = _get_global_magnifier_drawer()

    def _get_highlighted_color(self, color: Tuple[int, int, int, int], is_highlighted: bool) -> Tuple[int, int, int, int]:
        if not is_highlighted:
            return color

        return (
            min(255, color[0] + 50),
            min(255, color[1] + 50),
            min(255, color[2] + 50),
            min(255, color[3] + 30)
        )

    def render_frame(self, ctx: RenderContext) -> Tuple[Optional[Image.Image], int, int, Optional[QRect], Optional[QPoint], Optional[Image.Image]]:

        img1_scaled = ctx.image1
        img2_scaled = ctx.image2

        if not img1_scaled and not img2_scaled:

            placeholder = Image.new("RGBA", (ctx.width if ctx.width > 0 else 1, ctx.height if ctx.height > 0 else 1), (0, 0, 0, 0))
            return placeholder, 0, 0, None, None, None

        if img1_scaled:
            target_size = img1_scaled.size
        else:
            target_size = img2_scaled.size

        if not img1_scaled:
            img1_scaled = Image.new("RGBA", target_size, (0, 0, 0, 0))
        if not img2_scaled:
            img2_scaled = Image.new("RGBA", target_size, (0, 0, 0, 0))

        if img1_scaled.size != img2_scaled.size:
             if img1_scaled.size == target_size:
                 img2_scaled = img2_scaled.resize(target_size, Image.Resampling.NEAREST)
             else:
                 img1_scaled = img1_scaled.resize(target_size, Image.Resampling.NEAREST)

        try:
            img_w, img_h = img1_scaled.size
            padding_left, padding_top = 0, 0
            canvas_w, canvas_h = img_w, img_h
            magnifier_bbox_on_canvas = None

            if ctx.use_magnifier and ctx.magnifier_drawing_coords:
                magnifier_bbox = ctx.magnifier_drawing_coords[-1]
                if magnifier_bbox and isinstance(magnifier_bbox, QRect) and magnifier_bbox.isValid():
                    padding_left = abs(min(0, magnifier_bbox.left()))
                    padding_top = abs(min(0, magnifier_bbox.top()))
                    padding_right = max(0, magnifier_bbox.right() - img_w)
                    padding_bottom = max(0, magnifier_bbox.bottom() - img_h)
                    canvas_w = img_w + padding_left + padding_right
                    canvas_h = img_h + padding_top + padding_bottom
                    magnifier_bbox_on_canvas = magnifier_bbox.translated(padding_left, padding_top)

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

                tuple(ctx.divider_line_color) if isinstance(ctx.divider_line_color, (list, tuple)) else ctx.divider_line_color
            )

            if ctx.background_cache_dict is not None:
                if "last_key" in ctx.background_cache_dict and ctx.background_cache_dict["last_key"] == current_bg_key:
                    base_image = ctx.background_cache_dict.get("image")

            if base_image is None:
                base_image = self._create_base_image(ctx, img1_scaled, img2_scaled)

                if ctx.background_cache_dict is not None and base_image:
                    ctx.background_cache_dict["last_key"] = current_bg_key
                    ctx.background_cache_dict["image"] = base_image

            if not base_image:
                return None, 0, 0, None, None, None

            final_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            final_canvas.paste(base_image, (padding_left, padding_top))

            if ctx.divider_line_visible and ctx.divider_line_thickness > 0 and ctx.diff_mode == 'off':
                self._draw_divider_line_on_canvas(ctx, final_canvas, padding_left, padding_top, img_w, img_h)

            combined_center_point = None

            if ctx.use_magnifier and ctx.show_capture_area:

                from shared.image_processing.pipeline import _clamp_capture_position

                ref_dim = min(img_w, img_h)
                cap_size = max(5, int(round(ctx.capture_size * ref_dim)))

                clamped_x, clamped_y = _clamp_capture_position(
                    ctx.magnifier_pos.x(), ctx.magnifier_pos.y(),
                    img_w, img_h, ctx.capture_size
                )
                cap_x = padding_left + int(round(clamped_x * img_w))
                cap_y = padding_top + int(round(clamped_y * img_h))

                capture_color = self._get_highlighted_color(
                    ctx.capture_ring_color,
                    ctx.highlighted_magnifier_element == "capture"
                )

                self.magnifier_drawer.draw_capture_area(
                    final_canvas, QPoint(cap_x, cap_y), cap_size,
                    color=capture_color
                )

            if ctx.use_magnifier and ctx.magnifier_drawing_coords:
                combined_center_point = self._draw_magnifier_full(ctx, final_canvas, img1_scaled, img2_scaled,
                                                                   padding_left, padding_top, img_w, img_h)

            if ctx.include_file_names:
                self._draw_file_names_on_canvas(ctx, final_canvas, padding_left, padding_top, img_w, img_h)

            return final_canvas, padding_left, padding_top, magnifier_bbox_on_canvas, combined_center_point, None

        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            return None, 0, 0, None, None, None

    def _resize_images(self, ctx: RenderContext) -> Tuple[Image.Image, Image.Image]:
        target_size = (ctx.width, ctx.height)

        if ctx.image1.size == target_size and ctx.image2.size == target_size:
            return ctx.image1, ctx.image2

        img1_resized = ctx.image1.resize(target_size, self._get_resize_filter(ctx.interpolation_method))
        img2_resized = ctx.image2.resize(target_size, self._get_resize_filter(ctx.interpolation_method))

        return img1_resized, img2_resized

    def _get_resize_filter(self, method: str) -> Image.Resampling:
        mapping = {
            "NEAREST": Image.Resampling.NEAREST,
            "BILINEAR": Image.Resampling.BILINEAR,
            "BICUBIC": Image.Resampling.BICUBIC,
            "LANCZOS": Image.Resampling.LANCZOS,
            "EWA_LANCZOS": Image.Resampling.LANCZOS,
        }
        return mapping.get(method.upper(), Image.Resampling.BILINEAR)

    def _create_base_image(self, ctx: RenderContext, img1: Image.Image, img2: Image.Image) -> Optional[Image.Image]:

        if ctx.channel_view_mode != 'RGB':
            img1 = extract_channel(img1, ctx.channel_view_mode) or img1
            img2 = extract_channel(img2, ctx.channel_view_mode) or img2

        if ctx.diff_mode != 'off':
            return self._apply_diff_mode(ctx, img1, img2)
        else:
            return self._create_split_image(ctx, img1, img2)

    def _apply_diff_mode(self, ctx: RenderContext, img1: Image.Image, img2: Image.Image) -> Optional[Image.Image]:
        if ctx.diff_mode == 'edges':
            edge_map1 = create_edge_map(img1) or img1
            edge_map2 = create_edge_map(img2) or img2
            return self._create_split_image(ctx, edge_map1, edge_map2)
        elif ctx.diff_mode == 'highlight':
            return create_highlight_diff(img1, img2, threshold=10, font_path=self.font_path)
        elif ctx.diff_mode == 'grayscale':
            return create_grayscale_diff(img1, img2, font_path=self.font_path)
        elif ctx.diff_mode == 'ssim':
            return create_ssim_map(img1, img2, font_path=self.font_path)
        else:
            return self._create_split_image(ctx, img1, img2)

    def _create_split_image(self, ctx: RenderContext, img1: Image.Image, img2: Image.Image) -> Optional[Image.Image]:
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

    def _draw_divider_line_on_canvas(self, ctx: RenderContext, canvas: Image.Image,
                                     padding_left: int, padding_top: int,
                                     img_w: int, img_h: int):
        """Рисует разделительную линию на канвасе с учетом padding."""
        draw = ImageDraw.Draw(canvas)

        if not ctx.is_horizontal:
            x = padding_left + int(round(img_w * ctx.split_pos))
            draw.rectangle([
                x - ctx.divider_line_thickness // 2,
                padding_top,
                x + (ctx.divider_line_thickness + 1) // 2 - 1,
                padding_top + img_h - 1
            ], fill=ctx.divider_line_color)
        else:
            y = padding_top + int(round(img_h * ctx.split_pos))
            draw.rectangle([
                padding_left,
                y - ctx.divider_line_thickness // 2,
                padding_left + img_w - 1,
                y + (ctx.divider_line_thickness + 1) // 2 - 1
            ], fill=ctx.divider_line_color)

    def _draw_magnifier_full(self, ctx: RenderContext, canvas: Image.Image,
                            img1_scaled: Image.Image, img2_scaled: Image.Image,
                            padding_left: int, padding_top: int, img_w: int, img_h: int) -> Optional[QPoint]:
        """Рисует полную лупу с guides и всем необходимым. Возвращает combined_center_point."""
        if not ctx.magnifier_drawing_coords:
            return None

        combined_center_point = None

        if ctx.magnifier_drawing_coords[2] is not None:
            mag_mid_on_canvas = QPoint(
                ctx.magnifier_drawing_coords[2].x() + padding_left,
                ctx.magnifier_drawing_coords[2].y() + padding_top
            )

            if ctx.show_magnifier_guides:
                self._draw_magnifier_guides(ctx, canvas, mag_mid_on_canvas,
                                           padding_left, padding_top, img_w, img_h)

            original_img1 = ctx.original_image1 or img1_scaled
            original_img2 = ctx.original_image2 or img2_scaled

            from core.store import Store
            from PyQt6.QtGui import QColor
            temp_store = Store()
            temp_store.viewport.magnifier_visible_left = ctx.magnifier_visible_left

            is_visual_diff = ctx.diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')
            temp_store.viewport.magnifier_visible_center = ctx.magnifier_visible_center if not is_visual_diff else True
            temp_store.viewport.magnifier_visible_right = ctx.magnifier_visible_right
            temp_store.viewport.magnifier_is_horizontal = ctx.magnifier_is_horizontal
            temp_store.viewport.diff_mode = ctx.diff_mode

            magnifier_interpolation = ctx.interpolation_method

            if ctx.is_interactive_mode and ctx.magnifier_movement_interpolation_method:

                 magnifier_interpolation = ctx.magnifier_movement_interpolation_method

            interactive_center_local = self.magnifier_drawer.draw_magnifier(
                temp_store, canvas,
                original_img1, original_img2,
                ctx.magnifier_drawing_coords[0], ctx.magnifier_drawing_coords[1],
                mag_mid_on_canvas,
                ctx.magnifier_drawing_coords[3],
                ctx.magnifier_drawing_coords[4],
                magnifier_interpolation, ctx.is_horizontal,
                ctx.is_magnifier_combined,
                is_interactive_render=ctx.is_interactive_mode,
                internal_split=ctx.magnifier_internal_split,
                divider_visible=ctx.magnifier_divider_visible,
                divider_color=ctx.magnifier_divider_color,
                divider_thickness=ctx.magnifier_divider_thickness,
                border_color=self._get_highlighted_color(ctx.magnifier_border_color, ctx.highlighted_magnifier_element == "border"),
                capture_ring_color=ctx.capture_ring_color,
                font_path=self.font_path,

                external_cache=ctx.magnifier_cache_dict
            )

            if interactive_center_local:
                combined_center_point = QPoint(
                    interactive_center_local.x() - padding_left,
                    interactive_center_local.y() - padding_top
                )

        return combined_center_point

    def _draw_magnifier_guides(self, ctx: RenderContext, canvas: Image.Image,
                               mag_mid_on_canvas: QPoint, padding_left: int, padding_top: int,
                               img_w: int, img_h: int):
        """Рисует guides (лазеры) от лупы к области захвата."""

        if ctx.magnifier_guides_thickness == 0:
            return

        if not ctx.show_magnifier_guides:
            return

        import math

        laser_centers = []
        mid_x, mid_y = mag_mid_on_canvas.x(), mag_mid_on_canvas.y()
        mag_size = ctx.magnifier_drawing_coords[3]
        spacing = ctx.magnifier_drawing_coords[4]

        is_visual_diff = ctx.diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')

        if ctx.is_magnifier_combined:
            if is_visual_diff:

                laser_centers.append(mag_mid_on_canvas)

                if not ctx.is_horizontal:
                    combined_y = int(round(mid_y + mag_size + 8))
                    laser_centers.append(QPoint(mid_x, combined_y))
                else:
                    combined_x = int(round(mid_x + mag_size + 8))
                    laser_centers.append(QPoint(combined_x, mid_y))
            else:

                laser_centers.append(mag_mid_on_canvas)
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

        clamped_x, clamped_y = _clamp_capture_position(
            ctx.magnifier_pos.x(), ctx.magnifier_pos.y(),
            img_w, img_h, ctx.capture_size
        )
        cap_x = padding_left + int(round(clamped_x * img_w))
        cap_y = padding_top + int(round(clamped_y * img_h))
        p_cap = QPoint(cap_x, cap_y)

        laser_color = self._get_highlighted_color(
            ctx.magnifier_laser_color,
            ctx.highlighted_magnifier_element == "laser"
        )

        is_interactive = ctx.is_interactive_mode
        optimize_smoothing = ctx.optimize_laser_smoothing

        if is_interactive:
            if optimize_smoothing:

                interpolation_method = ctx.laser_smoothing_interpolation_method
                should_smooth = True
            else:
                interpolation_method = 'LANCZOS'
                should_smooth = False
        else:

            interpolation_method = 'LANCZOS'
            should_smooth = True

        for p_mag in laser_centers:
            if p_mag:
                thickness = ctx.magnifier_guides_thickness

                self._draw_aa_laser(canvas, p_mag, p_cap, r_mag, r_cap, laser_color, not should_smooth, thickness, interpolation_method)

    def _draw_aa_laser(self, canvas: Image.Image, p1: QPoint, p2: QPoint,
                      r1: float, r2: float, color: Tuple[int, int, int, int],
                      is_interactive: bool, thickness: int = 1, interpolation_method: str = "BILINEAR"):
        """Рисует сглаженную линию между двумя точками.

        Args:
            is_interactive: Если True - рисует без сглаживания (быстрый режим),
                          Если False - рисует со сглаживанием (качественный режим)
            interpolation_method: Метод интерполяции для сглаживания (используется только когда is_interactive=False)
        """
        import math

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
            draw.line([(ax, ay), (bx, by)], fill=opaque_color, width=thickness)
        else:
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
                width=thickness * scale
            )

            resize_filter = self._get_resize_filter(interpolation_method)
            smooth_line = hr_canvas.resize((bbox_w, bbox_h), resize_filter)

            canvas.alpha_composite(smooth_line, (left, top))

    def _draw_capture_area(self, image: Image.Image, center: Tuple[int, int], size: int):
        draw = ImageDraw.Draw(image)
        x, y = center
        half_size = size // 2

        draw.rectangle([
            x - half_size, y - half_size,
            x + half_size, y + half_size
        ], outline=(255, 255, 255, 200), width=2)

    def _draw_magnifier_circles(self, ctx: RenderContext, base_image: Image.Image,
                              img1: Image.Image, img2: Image.Image,
                              center: Tuple[int, int], magnifier_size: int, capture_size: int, mag_pos: Tuple[int, int] = None):
        """Draw magnifier circles with captured content."""

        x, y = center
        half_magnifier = magnifier_size // 2

        if mag_pos:
            mag_x, mag_y = mag_pos
        else:
            mag_x, mag_y = x, y

        crop1 = self._calculate_crop_area(img1, center, capture_size, base_image.size)
        crop2 = self._calculate_crop_area(img2, center, capture_size, base_image.size)

        crop1_resized = crop1.resize((magnifier_size, magnifier_size),
                                   self._get_resize_filter(ctx.interpolation_method))
        crop2_resized = crop2.resize((magnifier_size, magnifier_size),
                                   self._get_resize_filter(ctx.interpolation_method))

        mask = self._create_circular_mask(magnifier_size, magnifier_size)

        crop1_masked = Image.composite(crop1_resized, Image.new("RGBA", crop1_resized.size, (0, 0, 0, 0)), mask)
        crop2_masked = Image.composite(crop2_resized, Image.new("RGBA", crop2_resized.size, (0, 0, 0, 0)), mask)

        base_image.paste(crop1_masked, (mag_x - half_magnifier, mag_y - half_magnifier), crop1_masked)
        base_image.paste(crop2_masked, (mag_x - half_magnifier, mag_y - half_magnifier), crop2_masked)

    def _calculate_crop_area(self, image: Image.Image, center: Tuple[int, int],
                           size: int, canvas_size: Tuple[int, int]) -> Image.Image:
        """Calculate and extract crop area from image."""
        img_width, img_height = image.size
        canvas_width, canvas_height = canvas_size

        scale_x = img_width / canvas_width if canvas_width > 0 else 1
        scale_y = img_height / canvas_height if canvas_height > 0 else 1

        img_center_x = int(round(center[0] * scale_x))
        img_center_y = int(round(center[1] * scale_y))

        safe_size = max(2, size)
        half_size = safe_size // 2

        left = max(0, img_center_x - half_size)
        top = max(0, img_center_y - half_size)

        right = max(left + 1, min(img_width, img_center_x + half_size))
        bottom = max(top + 1, min(img_height, img_center_y + half_size))

        return image.crop((left, top, right, bottom))

    def _create_circular_mask(self, width: int, height: int) -> Image.Image:
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([0, 0, width, height], fill=255)
        return mask

    def _draw_file_names_on_canvas(self, ctx: RenderContext, canvas: Image.Image,
                                   padding_left: int, padding_top: int, img_w: int, img_h: int):
        """Рисует имена файлов на канвасе."""
        from core.store import Store
        from PyQt6.QtGui import QColor

        temp_store = Store()
        temp_store.viewport.include_file_names_in_saved = True
        temp_store.viewport.is_horizontal = ctx.is_horizontal
        temp_store.viewport.text_placement_mode = ctx.text_placement_mode
        temp_store.viewport.draw_text_background = ctx.draw_text_background
        temp_store.viewport.font_size_percent = ctx.font_size_percent
        temp_store.viewport.font_weight = ctx.font_weight
        temp_store.viewport.text_alpha_percent = ctx.text_alpha_percent
        temp_store.viewport.file_name_color = QColor(*ctx.file_name_color)
        temp_store.viewport.file_name_bg_color = QColor(*ctx.file_name_bg_color)
        temp_store.viewport.max_name_length = ctx.max_name_length

        if not ctx.is_horizontal:
            split_pos = padding_left + int(img_w * ctx.split_pos)
        else:
            split_pos = padding_top + int(img_h * ctx.split_pos)

        image_rect = QRect(padding_left, padding_top, img_w, img_h)

        self.text_drawer.draw_filenames_on_image(
            temp_store,
            canvas,
            image_rect,
            split_pos,
            ctx.divider_line_thickness,
            ctx.file_name1,
            ctx.file_name2,
        )

def create_render_context_from_store(store, width: int, height: int,
                                     magnifier_drawing_coords: Optional[Tuple] = None,
                                     image1_scaled: Optional[Image.Image] = None,
                                     image2_scaled: Optional[Image.Image] = None) -> RenderContext:
    """
    Создает RenderContext из Store.

    Args:
        store: Store объект
        width: Ширина для рендеринга
        height: Высота для рендеринга
        magnifier_drawing_coords: Координаты для рисования лупы (опционально)
        image1_scaled: Масштабированное изображение 1 (если есть)
        image2_scaled: Масштабированное изображение 2 (если есть)
    """
    view = store.viewport.view_state
    render = store.viewport.render_config
    session = store.viewport.session_data

    viewport_thickness = getattr(store.viewport, 'magnifier_divider_thickness', None)
    render_config_thickness = render.magnifier_divider_thickness
    optimize_laser = getattr(render, 'optimize_laser_smoothing', False)

    main_interp = render.interpolation_method

    magnifier_movement_interp = getattr(render, 'magnifier_movement_interpolation_method', 'BILINEAR')
    laser_smoothing_interp = getattr(render, 'laser_smoothing_interpolation_method', 'BILINEAR')

    eff_mag_interp = _resolve_interpolation(main_interp, magnifier_movement_interp)
    eff_laser_interp = _resolve_interpolation(main_interp, laser_smoothing_interp)

    movement_interp = eff_mag_interp

    img1 = image1_scaled or session.image1 or getattr(store.document, 'original_image1', None) or Image.new("RGBA", (width, height))
    img2 = image2_scaled or session.image2 or getattr(store.document, 'original_image2', None) or Image.new("RGBA", (width, height))

    name1, name2 = "", ""

    try:
        if 0 <= store.document.current_index1 < len(store.document.image_list1):
            name1 = store.document.image_list1[store.document.current_index1].display_name
        if 0 <= store.document.current_index2 < len(store.document.image_list2):
            name2 = store.document.image_list2[store.document.current_index2].display_name
    except Exception:
        pass

    magnifier_offset = None
    if view.use_magnifier and view.magnifier_offset_relative_visual:
        ref_dim = min(width, height)
        offset_x = int(view.magnifier_offset_relative_visual.x() * ref_dim)
        offset_y = int(view.magnifier_offset_relative_visual.y() * ref_dim)
        magnifier_offset = QPoint(offset_x, offset_y)

    is_visual_diff = view.diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')
    magnifier_visible_center = view.magnifier_visible_center
    if is_visual_diff:
        magnifier_visible_center = True

    return RenderContext(
        width=width,
        height=height,
        image1=img1,
        image2=img2,
        split_pos=view.split_position_visual,
        magnifier_pos=view.capture_position_relative,
        magnifier_offset=magnifier_offset,
        diff_mode=view.diff_mode,
        channel_view_mode=view.channel_view_mode,
        is_horizontal=view.is_horizontal,
        use_magnifier=view.use_magnifier,
        magnifier_size=view.magnifier_size_relative,
        capture_size=view.capture_size_relative,
        show_capture_area=render.show_capture_area_on_main_image,
        divider_line_visible=render.divider_line_visible,
        divider_line_color=(
            render.divider_line_color.red(),
            render.divider_line_color.green(),
            render.divider_line_color.blue(),
            render.divider_line_color.alpha()
        ),
        divider_line_thickness=render.divider_line_thickness,
        include_file_names=render.include_file_names_in_saved,
        file_name1=name1,
        file_name2=name2,
        magnifier_is_horizontal=view.magnifier_is_horizontal,
        magnifier_divider_visible=render.magnifier_divider_visible,
        magnifier_divider_color=(
            render.magnifier_divider_color.red(),
            render.magnifier_divider_color.green(),
            render.magnifier_divider_color.blue(),
            render.magnifier_divider_color.alpha()
        ),
        magnifier_divider_thickness=render.magnifier_divider_thickness,
        magnifier_internal_split=view.magnifier_internal_split,
        interpolation_method=render.interpolation_method,
        original_image1=getattr(store.document, 'original_image1', None) or getattr(store.document, 'full_res_image1', None),
        original_image2=getattr(store.document, 'original_image2', None) or getattr(store.document, 'full_res_image2', None),
        magnifier_drawing_coords=magnifier_drawing_coords,
        magnifier_visible_left=view.magnifier_visible_left,
        magnifier_visible_center=magnifier_visible_center,
        magnifier_visible_right=view.magnifier_visible_right,
        is_magnifier_combined=view.is_magnifier_combined,
        magnifier_border_color=(
            render.magnifier_border_color.red(),
            render.magnifier_border_color.green(),
            render.magnifier_border_color.blue(),
            render.magnifier_border_color.alpha()
        ),
        magnifier_laser_color=(
            render.magnifier_laser_color.red(),
            render.magnifier_laser_color.green(),
            render.magnifier_laser_color.blue(),
            render.magnifier_laser_color.alpha()
        ),
        capture_ring_color=(
            render.capture_ring_color.red(),
            render.capture_ring_color.green(),
            render.capture_ring_color.blue(),
            render.capture_ring_color.alpha()
        ),
        show_magnifier_guides=render.show_magnifier_guides,
        magnifier_guides_thickness=render.magnifier_guides_thickness,
        is_interactive_mode=view.is_interactive_mode,
        optimize_laser_smoothing=render.optimize_laser_smoothing,
        movement_interpolation_method=eff_mag_interp,
        magnifier_movement_interpolation_method=eff_mag_interp,
        laser_smoothing_interpolation_method=eff_laser_interp,
        magnifier_offset_relative_visual=view.magnifier_offset_relative_visual,
        magnifier_spacing_relative_visual=view.magnifier_spacing_relative_visual,
        highlighted_magnifier_element=getattr(view, 'highlighted_magnifier_element', None),
        font_size_percent=render.font_size_percent,
        font_weight=render.font_weight,
        text_alpha_percent=render.text_alpha_percent,
        file_name_color=(
            render.file_name_color.red(),
            render.file_name_color.green(),
            render.file_name_color.blue(),
            render.file_name_color.alpha()
        ),
        file_name_bg_color=(
            render.file_name_bg_color.red(),
            render.file_name_bg_color.green(),
            render.file_name_bg_color.blue(),
            render.file_name_bg_color.alpha()
        ),
        draw_text_background=render.draw_text_background,
        text_placement_mode=render.text_placement_mode,
        max_name_length=render.max_name_length
    )

def create_render_context_from_params(render_params_dict: dict, width: int, height: int,
                                     magnifier_drawing_coords: Optional[Tuple] = None,
                                     image1_scaled: Optional[Image.Image] = None,
                                     image2_scaled: Optional[Image.Image] = None,
                                     original_image1: Optional[Image.Image] = None,
                                     original_image2: Optional[Image.Image] = None,
                                     file_name1: str = "",
                                     file_name2: str = "",
                                     session_caches: dict = None) -> RenderContext:
    """
    Создает RenderContext из словаря параметров (легковесная альтернатива create_render_context_from_store).

    Args:
        render_params_dict: Словарь с параметрами рендеринга (полученный из viewport.get_render_params())
        width: Ширина для рендеринга
        height: Высота для рендеринга
        magnifier_drawing_coords: Координаты для рисования лупы (опционально)
        image1_scaled: Масштабированное изображение 1 (если есть)
        image2_scaled: Масштабированное изображение 2 (если есть)
        original_image1: Оригинальное изображение 1 (опционально)
        original_image2: Оригинальное изображение 2 (опционально)
        file_name1: Имя файла 1
        file_name2: Имя файла 2
    """
    params = render_params_dict

    img1 = image1_scaled or original_image1 or Image.new("RGBA", (width, height), (0, 0, 0, 255))
    img2 = image2_scaled or original_image2 or Image.new("RGBA", (width, height), (0, 0, 0, 255))

    mag_pos_tuple = params.get('magnifier_pos', (0.5, 0.5))
    if isinstance(mag_pos_tuple, tuple) and len(mag_pos_tuple) >= 2:

        mag_pos = QPointF(float(mag_pos_tuple[0]), float(mag_pos_tuple[1]))
    elif isinstance(mag_pos_tuple, QPointF):
        mag_pos = QPointF(mag_pos_tuple)
    else:
        mag_pos = QPointF(0.5, 0.5)

    magnifier_offset = None
    if params.get('use_magnifier') and params.get('magnifier_offset_relative_visual'):
        ref_dim = min(width, height)
        mag_offset_visual = params['magnifier_offset_relative_visual']
        if isinstance(mag_offset_visual, tuple):
            offset_x = int(mag_offset_visual[0] * ref_dim)
            offset_y = int(mag_offset_visual[1] * ref_dim)
        elif isinstance(mag_offset_visual, QPointF):
            offset_x = int(mag_offset_visual.x() * ref_dim)
            offset_y = int(mag_offset_visual.y() * ref_dim)
        else:
            offset_x = offset_y = 0
        magnifier_offset = QPoint(offset_x, offset_y)

    mag_offset_relative_visual_qpoint = None
    if params.get('magnifier_offset_relative_visual'):
        mag_offset_visual = params['magnifier_offset_relative_visual']
        if isinstance(mag_offset_visual, tuple):
            mag_offset_relative_visual_qpoint = QPointF(float(mag_offset_visual[0]), float(mag_offset_visual[1]))
        elif isinstance(mag_offset_visual, QPointF):
            mag_offset_relative_visual_qpoint = QPointF(mag_offset_visual)

    is_visual_diff = params.get('diff_mode', 'off') in ('highlight', 'grayscale', 'ssim', 'edges')
    magnifier_visible_center = params.get('magnifier_visible_center', True)
    if is_visual_diff:
        magnifier_visible_center = True

    caches = session_caches or {}

    return RenderContext(
        width=width,
        height=height,
        image1=img1,
        image2=img2,
        split_pos=params.get('split_pos', 0.5),
        magnifier_pos=mag_pos,
        magnifier_offset=magnifier_offset,
        diff_mode=params.get('diff_mode', 'off'),
        channel_view_mode=params.get('channel_view_mode', 'RGB'),
        is_horizontal=params.get('is_horizontal', False),
        use_magnifier=params.get('use_magnifier', False),
        magnifier_size=params.get('magnifier_size_relative', 0.2),
        capture_size=params.get('capture_size_relative', 0.1),
        show_capture_area=params.get('show_capture_area_on_main_image', True),
        divider_line_visible=params.get('divider_line_visible', True),
        divider_line_color=params.get('divider_line_color', (255, 255, 255, 255)),
        divider_line_thickness=params.get('divider_line_thickness', 3),
        include_file_names=params.get('include_file_names_in_saved', False),
        file_name1=file_name1,
        file_name2=file_name2,
        magnifier_is_horizontal=params.get('magnifier_is_horizontal', False),
        magnifier_divider_visible=params.get('magnifier_divider_visible', True),
        magnifier_divider_color=params.get('magnifier_divider_color', (255, 255, 255, 230)),
        magnifier_divider_thickness=params.get('magnifier_divider_thickness', 2),
        magnifier_internal_split=params.get('magnifier_internal_split', 0.5),
        interpolation_method=params.get('interpolation_method', 'BILINEAR'),
        original_image1=original_image1,
        original_image2=original_image2,
        magnifier_drawing_coords=magnifier_drawing_coords,
        magnifier_visible_left=params.get('magnifier_visible_left', True),
        magnifier_visible_center=magnifier_visible_center,
        magnifier_visible_right=params.get('magnifier_visible_right', True),
        is_magnifier_combined=params.get('is_magnifier_combined', False),
        magnifier_border_color=params.get('magnifier_border_color', (255, 255, 255, 230)),
        magnifier_laser_color=params.get('magnifier_laser_color', (255, 255, 255, 255)),
        capture_ring_color=params.get('capture_ring_color', (255, 50, 100, 230)),
        show_magnifier_guides=params.get('show_magnifier_guides', False),
        magnifier_guides_thickness=params.get('magnifier_guides_thickness', 1),
        is_interactive_mode=params.get('is_interactive_mode', False),
        optimize_laser_smoothing=params.get('optimize_laser_smoothing', False),
        movement_interpolation_method=params.get('movement_interpolation_method', 'BILINEAR'),
        magnifier_movement_interpolation_method=params.get('magnifier_movement_interpolation_method', params.get('movement_interpolation_method', 'BILINEAR')),
        laser_smoothing_interpolation_method=params.get('laser_smoothing_interpolation_method', 'BILINEAR'),
        magnifier_offset_relative_visual=mag_offset_relative_visual_qpoint,
        magnifier_spacing_relative_visual=params.get('magnifier_spacing_relative_visual', 0.05),
        highlighted_magnifier_element=params.get('highlighted_magnifier_element'),
        font_size_percent=params.get('font_size_percent', 100),
        font_weight=params.get('font_weight', 0),
        text_alpha_percent=params.get('text_alpha_percent', 100),
        file_name_color=params.get('file_name_color', (255, 0, 0, 255)),
        file_name_bg_color=params.get('file_name_bg_color', (0, 0, 0, 80)),
        draw_text_background=params.get('draw_text_background', True),
        text_placement_mode=params.get('text_placement_mode', 'edges'),
        max_name_length=params.get('max_name_length', 50),
        magnifier_cache_dict=caches.get("magnifier"),
        background_cache_dict=caches.get("background")
    )
