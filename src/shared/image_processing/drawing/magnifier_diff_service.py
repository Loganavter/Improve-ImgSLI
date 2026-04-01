from PIL import Image

from plugins.analysis.processing import (
    create_edge_map,
    create_grayscale_diff,
    create_highlight_diff,
    create_ssim_map,
)

class MagnifierDiffService:
    def create_diff_image(
        self,
        image1: Image.Image,
        image2: Image.Image | None,
        mode: str = "highlight",
        threshold: int = 20,
        font_path: str | None = None,
    ) -> Image.Image | None:
        try:
            if mode == "edges":
                if not image1:
                    return None
                return create_edge_map(image1)

            if not image1 or image2 is None:
                return None

            if image1.size != image2.size:
                try:
                    image2 = image2.resize(image1.size, Image.Resampling.LANCZOS)
                except Exception:
                    return None

            diff_mode_handlers = {
                "ssim": lambda: create_ssim_map(image1, image2, font_path),
                "grayscale": lambda: create_grayscale_diff(image1, image2, font_path),
            }

            handler = diff_mode_handlers.get(mode)
            if handler:
                return handler()

            return create_highlight_diff(image1, image2, threshold, font_path)
        except Exception:
            return None
