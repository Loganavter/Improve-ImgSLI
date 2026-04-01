import logging
import math

from PIL import Image, ImageChops, ImageDraw
from PyQt6.QtCore import QPoint

from shared.image_processing.drawing.magnifier_diff import get_magnifier_content_size
from shared.image_processing.drawing.magnifier_layout import get_magnifier_sizes
from shared.image_processing.drawing.magnifier_masks import (
    create_framed_magnifier_widget,
    get_smooth_circular_mask,
    paste_magnifier_widget,
)

logger = logging.getLogger("ImproveImgSLI")

CAPTURE_THICKNESS_FACTOR = 0.1
MIN_CAPTURE_THICKNESS = 2.0
MAX_CAPTURE_THICKNESS = 8.0

class MagnifierCompositor:
    def draw_capture_area(
        self,
        image_to_draw_on: Image.Image,
        center_pos: QPoint,
        size: int,
        thickness: int | None = None,
        color: tuple = (255, 50, 100, 230),
    ):
        if (
            size <= 0
            or center_pos is None
            or not isinstance(image_to_draw_on, Image.Image)
        ):
            return

        try:
            if thickness is None or thickness <= 0:
                thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(
                    max(1.0, float(size))
                )
                thickness_clamped = max(
                    float(MIN_CAPTURE_THICKNESS),
                    min(float(MAX_CAPTURE_THICKNESS), thickness_float),
                )
                thickness = max(2, int(round(thickness_clamped)))

            outer_size = size
            inner_size = size - thickness * 2
            if inner_size <= 0:
                return

            outer_mask = get_smooth_circular_mask(outer_size)
            if not outer_mask:
                return

            inner_mask_on_canvas = Image.new("L", (outer_size, outer_size), 0)
            inner_mask_small = get_smooth_circular_mask(inner_size)
            if not inner_mask_small:
                return
            inner_mask_on_canvas.paste(inner_mask_small, (thickness, thickness))

            donut_mask = ImageChops.subtract(outer_mask, inner_mask_on_canvas)
        except Exception:
            return

        pastel_red_ring = Image.new("RGBA", (outer_size, outer_size), color)
        paste_pos_x = center_pos.x() - outer_size // 2
        paste_pos_y = center_pos.y() - outer_size // 2

        try:
            image_to_draw_on.paste(
                pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask
            )
        except Exception:
            pass

    def get_combined_magnifier_scaled_content(
        self,
        *,
        crop_service,
        crop_box1: tuple,
        crop_box2: tuple,
        content_size: int,
        interpolation_method: str,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        is_interactive_render: bool,
        external_cache: dict | None,
    ) -> tuple[Image.Image | None, Image.Image | None]:
        current_cache_key = (
            crop_box1,
            crop_box2,
            content_size,
            interpolation_method,
            image1_for_crop.size,
            image2_for_crop.size,
        )
        if (
            external_cache is not None
            and external_cache.get("key") == current_cache_key
        ):
            return external_cache.get("img1"), external_cache.get("img2")

        scaled1 = crop_service.get_normalized_content(
            image1_for_crop,
            crop_box1,
            content_size,
            interpolation_method,
            is_interactive_render,
        )
        scaled2 = crop_service.get_normalized_content(
            image2_for_crop,
            crop_box2,
            content_size,
            interpolation_method,
            is_interactive_render,
        )
        if external_cache is not None:
            external_cache["key"] = current_cache_key
            external_cache["img1"] = scaled1
            external_cache["img2"] = scaled2
        return scaled1, scaled2

    def build_combined_magnifier_composite(
        self,
        *,
        scaled1: Image.Image,
        scaled2: Image.Image,
        content_size: int,
        is_horizontal: bool,
        internal_split: float,
        divider_visible: bool,
        divider_color: tuple,
        divider_thickness: int,
    ) -> Image.Image | None:
        composite = scaled1.copy()
        if not is_horizontal:
            split_pos = int(content_size * internal_split)
            if split_pos < content_size:
                composite.paste(
                    scaled2.crop((split_pos, 0, content_size, content_size)),
                    (split_pos, 0),
                )
            self.draw_combined_divider(
                composite=composite,
                split_pos=split_pos,
                content_size=content_size,
                is_horizontal=False,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
        else:
            split_pos = int(content_size * internal_split)
            if split_pos < content_size:
                composite.paste(
                    scaled2.crop((0, split_pos, content_size, content_size)),
                    (0, split_pos),
                )
            self.draw_combined_divider(
                composite=composite,
                split_pos=split_pos,
                content_size=content_size,
                is_horizontal=True,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
        content_mask = get_smooth_circular_mask(content_size)
        if not content_mask:
            return None
        composite.putalpha(content_mask)
        return composite

    def draw_combined_divider(
        self,
        *,
        composite: Image.Image,
        split_pos: int,
        content_size: int,
        is_horizontal: bool,
        divider_visible: bool,
        divider_color: tuple,
        divider_thickness: int,
    ):
        if not divider_visible or divider_thickness <= 0:
            return
        draw = ImageDraw.Draw(composite)
        if not is_horizontal:
            x0 = split_pos - divider_thickness // 2
            x1 = x0 + divider_thickness - 1
            draw.rectangle([x0, 0, x1, content_size], fill=divider_color)
            return
        y0 = split_pos - divider_thickness // 2
        y1 = y0 + divider_thickness - 1
        draw.rectangle([0, y0, content_size, y1], fill=divider_color)

    def create_framed_magnifier_widget(
        self,
        *,
        composite: Image.Image,
        magnifier_size_pixels: int,
        border_width: int,
        border_color: tuple,
    ) -> Image.Image | None:
        return create_framed_magnifier_widget(
            composite=composite,
            magnifier_size_pixels=magnifier_size_pixels,
            border_width=border_width,
            border_color=border_color,
        )

    def paste_magnifier_widget(
        self,
        *,
        target_image: Image.Image,
        display_center_pos: QPoint,
        magnifier_widget: Image.Image | None,
    ):
        paste_magnifier_widget(
            target_image=target_image,
            display_center_pos=display_center_pos,
            magnifier_widget=magnifier_widget,
        )

    def draw_single_magnifier_circle(
        self,
        *,
        crop_service,
        target_image: Image.Image,
        display_center_pos: QPoint,
        crop_box_orig: tuple | None,
        magnifier_size_pixels: int,
        image_for_crop: Image.Image,
        interpolation_method: str,
        is_interactive_render: bool = False,
        border_color: tuple = (255, 255, 255, 255),
    ):
        if not isinstance(image_for_crop, Image.Image) or magnifier_size_pixels <= 0:
            return

        try:
            border_width = max(2, int(magnifier_size_pixels * 0.015))
            content_size = get_magnifier_content_size(magnifier_size_pixels)
            if content_size <= 0:
                return

            if crop_box_orig is not None:
                scaled_content = crop_service.get_normalized_content(
                    image_for_crop,
                    crop_box_orig,
                    content_size,
                    interpolation_method,
                    is_interactive_render,
                )
            else:
                scaled_content = image_for_crop
                if scaled_content.size != (content_size, content_size):
                    scaled_content = scaled_content.resize(
                        (content_size, content_size), Image.Resampling.LANCZOS
                    )

            content_mask = get_smooth_circular_mask(content_size)
            if not content_mask:
                return
            scaled_content.putalpha(content_mask)

            border_mask = get_smooth_circular_mask(magnifier_size_pixels)
            if not border_mask:
                return

            border_fill = Image.new(
                "RGB", (magnifier_size_pixels, magnifier_size_pixels), border_color[:3]
            )
            final_magnifier_widget = Image.new(
                "RGBA", (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0)
            )
            final_magnifier_widget.paste(border_fill, (0, 0), border_mask)

            content_paste_pos = border_width - 1
            final_magnifier_widget.alpha_composite(
                scaled_content, (content_paste_pos, content_paste_pos)
            )

            paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
            paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
            target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))
        except Exception:
            pass

    def draw_combined_magnifier_circle(
        self,
        *,
        crop_service,
        target_image: Image.Image,
        display_center_pos: QPoint,
        crop_box1: tuple,
        crop_box2: tuple,
        magnifier_size_pixels: int,
        image1_for_crop: Image.Image,
        image2_for_crop: Image.Image,
        interpolation_method: str,
        is_horizontal: bool,
        is_interactive_render: bool = False,
        internal_split: float = 0.5,
        divider_visible: bool = True,
        divider_color: tuple = (255, 255, 255, 230),
        divider_thickness: int = 2,
        border_color: tuple = (255, 255, 255, 255),
        external_cache: dict = None,
    ):
        if not all(
            [
                image1_for_crop,
                image2_for_crop,
                crop_box1,
                crop_box2,
                magnifier_size_pixels > 0,
            ]
        ):
            return

        try:
            border_width, content_size = get_magnifier_sizes(magnifier_size_pixels)
            if content_size <= 0:
                return

            scaled1, scaled2 = self.get_combined_magnifier_scaled_content(
                crop_service=crop_service,
                crop_box1=crop_box1,
                crop_box2=crop_box2,
                content_size=content_size,
                interpolation_method=interpolation_method,
                image1_for_crop=image1_for_crop,
                image2_for_crop=image2_for_crop,
                is_interactive_render=is_interactive_render,
                external_cache=external_cache,
            )
            if scaled1 is None or scaled2 is None:
                return

            composite = self.build_combined_magnifier_composite(
                scaled1=scaled1,
                scaled2=scaled2,
                content_size=content_size,
                is_horizontal=is_horizontal,
                internal_split=internal_split,
                divider_visible=divider_visible,
                divider_color=divider_color,
                divider_thickness=divider_thickness,
            )
            if composite is None:
                return

            self.paste_magnifier_widget(
                target_image=target_image,
                display_center_pos=display_center_pos,
                magnifier_widget=self.create_framed_magnifier_widget(
                    composite=composite,
                    magnifier_size_pixels=magnifier_size_pixels,
                    border_width=border_width,
                    border_color=border_color,
                ),
            )
        except Exception as exc:
            logger.error(
                f"Error in draw_combined_magnifier_circle: {exc}", exc_info=True
            )
