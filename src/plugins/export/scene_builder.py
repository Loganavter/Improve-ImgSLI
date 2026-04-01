from __future__ import annotations

from plugins.analysis.processing import (
    build_cached_diff_image,
    prepare_gl_background_layers_for_mode,
)
from plugins.export.models import ExportRenderContext
from shared.image_processing.resize import resize_images_processor
from utils.resource_loader import get_magnifier_drawing_coords

class ExportSceneBuilder:
    def __init__(self, store):
        self.store = store

    def build_resized_pair(self, image1, image2):
        resized1, resized2 = resize_images_processor(image1, image2)
        if not resized1 or not resized2:
            raise ValueError("Failed to unify images for saving.")
        return resized1, resized2

    def build_render_context(
        self,
        image1,
        image2,
        *,
        source_image1=None,
        source_image2=None,
        source_key=None,
        magnifier_drawing_coords=None,
        prepared_background_layers=None,
        cached_diff_image=None,
    ) -> ExportRenderContext:
        if image1 is None or image2 is None:
            raise ValueError("Export render context requires both images.")

        viewport = self.store.viewport
        width, height = image1.size
        diff_mode = str(getattr(viewport.view_state, "diff_mode", "off") or "off")
        channel_mode = str(getattr(viewport.view_state, "channel_view_mode", "RGB") or "RGB")

        if source_image1 is None:
            source_image1 = image1
        if source_image2 is None:
            source_image2 = image2
        if source_key is None:
            source_key = self._build_source_key(source_image1, source_image2)
        if magnifier_drawing_coords is None and getattr(viewport.view_state, "use_magnifier", False):
            magnifier_drawing_coords = get_magnifier_drawing_coords(
                store=self.store,
                drawing_width=width,
                drawing_height=height,
                container_width=width,
                container_height=height,
            )

        if prepared_background_layers is None and (
            diff_mode != "off" or channel_mode != "RGB"
        ):
            prepared_background_layers = prepare_gl_background_layers_for_mode(
                image1,
                image2,
                diff_mode,
                channel_mode,
            )

        if cached_diff_image is None and diff_mode != "off":
            cached_diff_image = build_cached_diff_image(
                image1,
                image2,
                diff_mode,
                channel_mode,
            )

        return ExportRenderContext(
            image1=image1,
            image2=image2,
            width=width,
            height=height,
            source_image1=source_image1,
            source_image2=source_image2,
            source_key=source_key,
            magnifier_drawing_coords=magnifier_drawing_coords,
            prepared_background_layers=prepared_background_layers,
            cached_diff_image=cached_diff_image,
        )

    def _build_source_key(self, source_image1, source_image2):
        document = getattr(self.store, "document", None)
        return (
            getattr(document, "image1_path", None),
            getattr(document, "image2_path", None),
            id(source_image1) if source_image1 is not None else 0,
            id(source_image2) if source_image2 is not None else 0,
            source_image1.size if source_image1 is not None else None,
            source_image2.size if source_image2 is not None else None,
        )
