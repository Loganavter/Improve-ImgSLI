from __future__ import annotations

import time

from PIL import Image

from plugins.export.scene_builder import ExportSceneBuilder
from shared.image_processing.prescale import prescale_pair
from ui.canvas_presentation.plan_builder import compute_canvas_plan
from plugins.video_editor.services.video_export_models import RenderedFrame, VideoRenderRequest
from ui.canvas_presentation import build_render_frame_presentation, build_snapshot_store_presentation

class SnapshotFrameRenderer:
    def __init__(self, image_loader, gpu_export_service=None) -> None:
        self._image_loader = image_loader
        self._gpu_export_service = gpu_export_service
        self._last_backend = "gpu"
        self._last_debug: dict = {}
        self._prescaled_cache: tuple | None = None

    @property
    def last_backend(self) -> str:
        return self._last_backend

    def reset_backend_state(self) -> None:
        self._last_backend = "gpu"
        self._prescaled_cache = None

    def drain_last_debug(self) -> dict:
        data = self._last_debug
        self._last_debug = {}
        return data

    def render(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        if self._gpu_export_service is None:
            raise RuntimeError("GPU export service is not configured")

        result = self._render_gpu(snap, request)
        self._last_backend = result.backend
        self._last_debug = result.debug
        return result

    def _resolve_images(self, snap, request: VideoRenderRequest):
        img1 = self._image_loader(snap.image1_path, request.auto_crop)
        img2 = self._image_loader(snap.image2_path, request.auto_crop)

        if not img1:
            img1 = Image.new(
                "RGBA",
                (max(1, request.output_width), max(1, request.output_height)),
                (50, 50, 50, 255),
            )
        if not img2:
            img2 = Image.new(
                "RGBA",
                (max(1, request.output_width), max(1, request.output_height)),
                (80, 80, 80, 255),
            )
        return img1, img2

    @staticmethod
    def _bounds_tuple(request: VideoRenderRequest):
        return request.global_bounds.as_tuple() if request.global_bounds is not None else None

    def _render_gpu(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        debug = {}
        skip_prescale = request.fit_content and request.global_bounds is not None
        cache_key = (
            snap.image1_path, snap.image2_path,
            request.output_width, request.output_height,
            skip_prescale,
        )
        if self._prescaled_cache is not None and self._prescaled_cache[0] == cache_key:
            img1, img2 = self._prescaled_cache[1], self._prescaled_cache[2]
            debug["load_ms"] = 0.0
            debug["prescale_ms"] = 0.0
        else:
            started = time.perf_counter()
            img1, img2 = self._resolve_images(snap, request)
            debug["load_ms"] = (time.perf_counter() - started) * 1000.0

            prescale_started = time.perf_counter()
            if not skip_prescale:
                img1, img2 = prescale_pair(img1, img2, request.output_width, request.output_height)
            debug["prescale_ms"] = (time.perf_counter() - prescale_started) * 1000.0
            self._prescaled_cache = (cache_key, img1, img2)

        build_store_started = time.perf_counter()
        presentation = build_snapshot_store_presentation(
            snap,
            img1,
            img2,
            fit_content=request.fit_content,
            global_bounds=self._bounds_tuple(request),
            fill_color=request.fill_rgba,
        )
        debug["build_store_ms"] = (time.perf_counter() - build_store_started) * 1000.0

        fit_resize_started = time.perf_counter()
        frame = build_render_frame_presentation(
            presentation,
            output_width=request.output_width,
            output_height=request.output_height,
        )
        debug["fit_resize_ms"] = (time.perf_counter() - fit_resize_started) * 1000.0

        scene_ctx_started = time.perf_counter()
        scene_builder = ExportSceneBuilder(frame.store)
        render_context = scene_builder.build_render_context(
            frame.scaled_image1,
            frame.scaled_image2,
            source_image1=frame.source_image1,
            source_image2=frame.source_image2,
            source_key=frame.source_key,
            overlay_drawing_coords=frame.feature_extras.get("overlay_drawing_coords"),
        )
        debug["scene_ctx_ms"] = (time.perf_counter() - scene_ctx_started) * 1000.0

        gpu_render_started = time.perf_counter()
        force_tiled, min_tiles_per_axis = self._get_gpu_tiling_config(
            request.output_width,
            request.output_height,
        )
        frame_pil, gpu_debug = self._gpu_export_service.render_image(
            store=frame.store,
            render_context=render_context,
            force_tiled=force_tiled,
            min_tiles_per_axis=min_tiles_per_axis,
        )
        debug["gpu_render_ms"] = (time.perf_counter() - gpu_render_started) * 1000.0
        debug.update(gpu_debug)
        if frame_pil is None:
            return RenderedFrame(
                image=Image.new("RGBA", (request.output_width, request.output_height), request.fill_rgba),
                backend="gpu",
                debug=debug,
            )

        composite_started = time.perf_counter()
        canvas_plan = compute_canvas_plan(
            frame.store,
            frame.render_width,
            frame.render_height,
            overlay_drawing_coords=frame.feature_extras.get("overlay_drawing_coords"),
        )
        pad_left = int(canvas_plan.padding_left)
        pad_top = int(canvas_plan.padding_top)
        crop_rect = (
            max(0, pad_left),
            max(0, pad_top),
            min(frame_pil.width, pad_left + frame.render_width),
            min(frame_pil.height, pad_top + frame.render_height),
        )
        base_image_content = frame_pil.crop(crop_rect)
        if base_image_content.size != (frame.render_width, frame.render_height):
            base_image_content = base_image_content.resize(
                (frame.render_width, frame.render_height),
                Image.Resampling.LANCZOS,
            )

        if (
            frame.image_dest_x == 0
            and frame.image_dest_y == 0
            and base_image_content.size == (request.output_width, request.output_height)
        ):
            debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
            return RenderedFrame(image=base_image_content, backend="gpu", debug=debug)

        final_frame = Image.new(
            "RGBA",
            (request.output_width, request.output_height),
            request.fill_rgba,
        )
        final_frame.alpha_composite(base_image_content, (frame.image_dest_x, frame.image_dest_y))
        debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
        return RenderedFrame(image=final_frame, backend="gpu", debug=debug)

    @staticmethod
    def _get_gpu_tiling_config(width: int, height: int) -> tuple[bool, int]:
        pixel_count = max(1, int(width)) * max(1, int(height))
        max_dim = max(int(width), int(height))
        if pixel_count >= 24_000_000 or max_dim >= 5500:
            return True, 3
        if pixel_count >= 14_000_000 or max_dim >= 4096:
            return True, 2
        return False, 1
