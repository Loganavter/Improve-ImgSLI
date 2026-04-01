import math

from PIL import Image

from shared.image_processing.regions import compute_centered_box
from shared.image_processing.resize import resample_image, resample_image_subpixel

MIN_CAPTURE_THICKNESS = 2.0

class MagnifierCropService:
    def should_use_subpixel(self, crop_box1: tuple, crop_box2: tuple) -> bool:
        try:
            size1 = abs((crop_box1[2] - crop_box1[0]) * (crop_box1[3] - crop_box1[1]))
            size2 = abs((crop_box2[2] - crop_box2[0]) * (crop_box2[3] - crop_box2[1]))
            if min(size1, size2) <= 0:
                return False

            ratio = max(size1, size2) / min(size1, size2)
            return ratio > 1.01
        except Exception:
            return False

    def compute_crop_boxes_subpixel(
        self, image1: Image.Image, image2: Image.Image, store
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
        try:
            w1, h1 = image1.size
            w2, h2 = image2.size

            box1 = self.compute_single_crop_box_subpixel(
                w1,
                h1,
                store.viewport.view_state.capture_position_relative.x,
                store.viewport.view_state.capture_position_relative.y,
                store.viewport.view_state.capture_size_relative,
            )
            box2 = self.compute_single_crop_box_subpixel(
                w2,
                h2,
                store.viewport.view_state.capture_position_relative.x,
                store.viewport.view_state.capture_position_relative.y,
                store.viewport.view_state.capture_size_relative,
            )

            return box1, box2
        except Exception:
            return ((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0))

    def compute_single_crop_box_subpixel(
        self,
        width: int,
        height: int,
        rel_x: float,
        rel_y: float,
        capture_size_relative: float,
    ) -> tuple[float, float, float, float]:
        ref_dim = min(width, height)
        thickness_display = max(
            int(MIN_CAPTURE_THICKNESS), int(round(ref_dim * 0.003))
        )
        capture_size_px = max(1, int(round(capture_size_relative * ref_dim)))
        inner_size = max(1, capture_size_px - thickness_display)

        max_square_size = max(1, min(width, height))
        inner_size = min(inner_size, max_square_size)
        if inner_size % 2 != 0:
            inner_size += 1
            inner_size = min(inner_size, max_square_size)

        return compute_centered_box(
            width=width,
            height=height,
            center_x=rel_x * width,
            center_y=rel_y * height,
            box_width=inner_size,
            box_height=inner_size,
        )

    def get_normalized_content(
        self,
        img: Image.Image,
        box: tuple,
        target_size: int,
        interpolation_method: str,
        is_interactive: bool,
    ) -> Image.Image:
        use_subpixel = self.should_use_subpixel(box, box)

        if use_subpixel:
            box_f = tuple(float(x) for x in box)
            return resample_image_subpixel(
                img,
                box_f,
                (target_size, target_size),
                interpolation_method,
                is_interactive,
                diff_mode_active=True,
            )

        return resample_image(
            img.crop(box),
            (target_size, target_size),
            interpolation_method,
            is_interactive,
            diff_mode_active=True,
        )
