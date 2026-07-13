from __future__ import annotations

import PIL.Image

from tabs.image_compare.plugins.video_editor.services.video_export_models import VideoRenderRequest
from shared.image_processing.resize import resize_images_processor
from shared.rendering import TargetSurfaceSpec, get_effective_export_interpolation_method
from tabs.image_compare.services.export_models import ExportSaveContext
from tabs.image_compare.services.live_snapshot import build_live_frame_snapshot
from tabs.image_compare.services.snapshot_render_plan_builder import (
    calculate_still_snapshot_bounds,
)
from tabs.image_compare.services.video_snapshot_rendering import SnapshotFrameRenderer


class ExportContextBuilder:
    def __init__(self, store, gpu_export_service, state_coordinator):
        self.store = store
        self.gpu_export_service = gpu_export_service
        self.state = state_coordinator
        self.renderer = SnapshotFrameRenderer(
            image_loader=lambda _path, _auto_crop=False: None,
            gpu_export_service=gpu_export_service,
        )

    def _current_canvas_fill_rgba(self):
        dialog_state = self.state.build_export_dialog_state()
        bg = dialog_state.background_color
        if not dialog_state.fill_background or bg is None:
            return None
        return (bg.r, bg.g, bg.b, bg.a)

    def has_images(self) -> bool:
        doc = self.store.get_session_state_slot("document")
        return bool(
            (doc.full_res_image1 or doc.original_image1 or doc.preview_image1)
            and (doc.full_res_image2 or doc.original_image2 or doc.preview_image2)
        )

    def build_save_context(self, include_preview: bool = True) -> ExportSaveContext:
        doc = self.store.get_session_state_slot("document")
        original1_full = doc.full_res_image1 or doc.original_image1 or doc.preview_image1
        original2_full = doc.full_res_image2 or doc.original_image2 or doc.preview_image2
        if not original1_full or not original2_full:
            raise ValueError("Full resolution images are not available for saving.")

        # docs/dev/rendering/tile-rendering-system.md Phase 3: saving/exporting
        # needs full pixel data regardless (resize, compositing), so
        # there's no way to avoid materializing a lazy source here -- but
        # it's a one-shot, user-triggered action, not a permanent
        # resident, so the transient cost is acceptable (same category as
        # the original decode itself).
        from shared.image_processing.lazy_pixel_source import LazyPixelSource

        if isinstance(original1_full, LazyPixelSource):
            original1_full = original1_full.to_pil()
        if isinstance(original2_full, LazyPixelSource):
            original2_full = original2_full.to_pil()

        preview_img = None
        live_snapshot = build_live_frame_snapshot(self.store)
        resize_method = get_effective_export_interpolation_method(
            live_snapshot.viewport_state
        )
        if include_preview:
            preview_img = self.build_export_preview_from_sources(
                original1_full,
                original2_full,
                live_snapshot=live_snapshot,
            )

        image1_for_save, image2_for_save = resize_images_processor(
            original1_full,
            original2_full,
            resize_method,
        )
        if not image1_for_save or not image2_for_save:
            raise ValueError("Failed to unify images for export.")
        global_bounds = calculate_still_snapshot_bounds(
            live_snapshot,
            image1_for_save,
            image2_for_save,
        )
        canvas_w = (
            int(global_bounds.base_width)
            + int(global_bounds.pad_left)
            + int(global_bounds.pad_right)
        )
        canvas_h = (
            int(global_bounds.base_height)
            + int(global_bounds.pad_top)
            + int(global_bounds.pad_bottom)
        )
        prepared_frame = self.renderer.prepare_canvas_frame_from_images(
            live_snapshot,
            VideoRenderRequest(
                target_surface=TargetSurfaceSpec(
                    width=canvas_w,
                    height=canvas_h,
                    fill_rgba=self._current_canvas_fill_rgba(),
                ),
                font_path=None,
                auto_crop=False,
                fit_content=True,
                global_bounds=global_bounds,
            ),
            image1_for_save,
            image2_for_save,
            allow_feature_layout_fallback=True,
            normalize_snapshot=False,
        )

        plan = prepared_frame.plan
        native_w = int(getattr(plan, "canvas_w", 0) or image1_for_save.width)
        native_h = int(getattr(plan, "canvas_h", 0) or image1_for_save.height)
        return ExportSaveContext(
            original1_full=original1_full,
            original2_full=original2_full,
            image1_for_save=image1_for_save,
            image2_for_save=image2_for_save,
            render_plan=plan,
            render_store=prepared_frame.store,
            preview_img=preview_img,
            suggested_filename=self.state.build_suggested_export_filename(),
            native_width=native_w,
            native_height=native_h,
        )

    def _downscale_for_preview(
        self,
        image: PIL.Image.Image,
        max_edge: int = 1200,
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

    def build_export_preview_from_sources(
        self,
        image1_full,
        image2_full,
        *,
        live_snapshot=None,
    ):
        live_snapshot = live_snapshot or build_live_frame_snapshot(self.store)
        resize_method = get_effective_export_interpolation_method(
            live_snapshot.viewport_state
        )
        image1_preview_src = self._downscale_for_preview(image1_full)
        image2_preview_src = self._downscale_for_preview(image2_full)
        image1_preview, image2_preview = resize_images_processor(
            image1_preview_src,
            image2_preview_src,
            resize_method,
        )
        if not image1_preview or not image2_preview:
            raise ValueError("Failed to build preview export pair.")
        global_bounds = calculate_still_snapshot_bounds(
            live_snapshot,
            image1_preview,
            image2_preview,
        )
        canvas_w = (
            int(global_bounds.base_width)
            + int(global_bounds.pad_left)
            + int(global_bounds.pad_right)
        )
        canvas_h = (
            int(global_bounds.base_height)
            + int(global_bounds.pad_top)
            + int(global_bounds.pad_bottom)
        )
        result = self.renderer.render_from_images(
            live_snapshot,
            VideoRenderRequest(
                target_surface=TargetSurfaceSpec(
                    width=canvas_w,
                    height=canvas_h,
                    fill_rgba=self._current_canvas_fill_rgba(),
                ),
                font_path=None,
                auto_crop=False,
                fit_content=True,
                global_bounds=global_bounds,
            ),
            image1_preview,
            image2_preview,
            allow_feature_layout_fallback=True,
            normalize_snapshot=False,
        )
        return result.image
