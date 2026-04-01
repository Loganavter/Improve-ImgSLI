from __future__ import annotations

import PIL.Image

from plugins.export.models import ExportSaveContext
from plugins.export.scene_builder import ExportSceneBuilder

class ExportContextBuilder:
    def __init__(self, store, gpu_export_service, state_coordinator):
        self.store = store
        self.gpu_export_service = gpu_export_service
        self.state = state_coordinator
        self.scene_builder = ExportSceneBuilder(store)

    def has_images(self) -> bool:
        doc = self.store.document
        return bool(
            (doc.full_res_image1 or doc.original_image1 or doc.preview_image1)
            and (doc.full_res_image2 or doc.original_image2 or doc.preview_image2)
        )

    def build_save_context(self, include_preview: bool = True) -> ExportSaveContext:
        original1_full = (
            self.store.document.full_res_image1
            or self.store.document.original_image1
            or self.store.document.preview_image1
        )
        original2_full = (
            self.store.document.full_res_image2
            or self.store.document.original_image2
            or self.store.document.preview_image2
        )
        if not original1_full or not original2_full:
            raise ValueError("Full resolution images are not available for saving.")

        preview_img = None
        if include_preview:
            preview_img = self.build_export_preview_from_sources(
                original1_full, original2_full
            )

        image1_for_save, image2_for_save = self.scene_builder.build_resized_pair(
            original1_full, original2_full
        )
        render_context = self.scene_builder.build_render_context(
            image1_for_save,
            image2_for_save,
            source_image1=original1_full,
            source_image2=original2_full,
        )

        return ExportSaveContext(
            original1_full=original1_full,
            original2_full=original2_full,
            image1_for_save=image1_for_save,
            image2_for_save=image2_for_save,
            magnifier_coords_for_save=render_context.magnifier_drawing_coords,
            render_context=render_context,
            preview_img=preview_img,
            suggested_filename=self.state.build_suggested_export_filename(),
        )

    def _downscale_for_preview(
        self, image: PIL.Image.Image, max_edge: int = 1200
    ) -> PIL.Image.Image:
        width, height = image.size
        longest_edge = max(width, height)
        if longest_edge <= max_edge:
            return image.copy()

        scale = max_edge / float(longest_edge)
        preview_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        return image.resize(preview_size, PIL.Image.Resampling.LANCZOS)

    def build_export_preview_from_sources(self, image1_full, image2_full):
        image1_preview_src = self._downscale_for_preview(image1_full)
        image2_preview_src = self._downscale_for_preview(image2_full)
        image1_preview, image2_preview = self.scene_builder.build_resized_pair(
            image1_preview_src, image2_preview_src
        )
        preview_context = self.scene_builder.build_render_context(
            image1_preview,
            image2_preview,
            source_image1=image1_preview_src,
            source_image2=image2_preview_src,
        )
        preview_img, _gpu_debug = self.gpu_export_service.render_image(
            store=self.store,
            render_context=preview_context,
        )
        if preview_img is None:
            raise RuntimeError("GPU export preview returned no image")
        return preview_img

    def build_export_preview(self, render_context):
        save_width, save_height = render_context.width, render_context.height
        preview_scale = max(1, min(5, max(save_width, save_height) // 800))
        preview_w = max(1, save_width // preview_scale)
        preview_h = max(1, save_height // preview_scale)
        image1_preview = render_context.image1.resize(
            (preview_w, preview_h), PIL.Image.Resampling.BILINEAR
        )
        image2_preview = render_context.image2.resize(
            (preview_w, preview_h), PIL.Image.Resampling.BILINEAR
        )
        preview_context = self.scene_builder.build_render_context(
            image1_preview,
            image2_preview,
            source_image1=image1_preview,
            source_image2=image2_preview,
        )
        preview_img, _gpu_debug = self.gpu_export_service.render_image(
            store=self.store,
            render_context=preview_context,
        )
        if preview_img is None:
            raise RuntimeError("GPU export preview returned no image")
        return preview_img
