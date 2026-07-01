from __future__ import annotations

import time
from dataclasses import dataclass

from PIL import Image

from core.tracing import Tracer
from plugins.video_editor.services.video_export_models import (
    GlobalCanvasBounds,
    RenderedFrame,
    VideoRenderRequest,
)
from shared.image_processing.prescale import prescale_pair
from shared.image_processing.resize import resample_image
from shared.rendering import get_effective_export_interpolation_method


@dataclass(slots=True)
class PreparedCanvasFrame:
    store: object
    plan: object
    output_width: int
    output_height: int
    image_dest_x: int
    image_dest_y: int
    fill_rgba: tuple[int, int, int, int]
    debug: dict


class SnapshotFrameRenderer:
    def __new__(cls, *args, **kwargs):
        if cls is not SnapshotFrameRenderer:
            return super().__new__(cls)
        renderer = _create_tab_snapshot_renderer(*args, **kwargs)
        if renderer is None:
            raise RuntimeError("No tab provided a snapshot frame renderer")
        return renderer

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

    @staticmethod
    def _trace(kind: str, summary: str, payload: dict) -> None:
        if Tracer.enabled():
            Tracer.instance().record(kind, summary, payload)

    @staticmethod
    def _resolve_prescale_target(
        request: VideoRenderRequest,
    ) -> tuple[int, int]:
        target_w = max(1, int(request.target_surface.width))
        target_h = max(1, int(request.target_surface.height))
        bounds = request.global_bounds
        if bounds is None:
            return target_w, target_h

        span_x = max(
            1.0,
            float(getattr(bounds, "canvas_x_max", 1.0))
            - float(getattr(bounds, "canvas_x_min", 0.0)),
        )
        span_y = max(
            1.0,
            float(getattr(bounds, "canvas_y_max", 1.0))
            - float(getattr(bounds, "canvas_y_min", 0.0)),
        )
        required_base_w = max(1, int(round(float(target_w) / span_x)))
        required_base_h = max(1, int(round(float(target_h) / span_y)))
        return (
            max(target_w, required_base_w),
            max(target_h, required_base_h),
        )

    @staticmethod
    def _fit_source_to_content(
        source: Image.Image,
        content_size: tuple[int, int],
        fill_rgba: tuple[int, int, int, int] | None = None,
        resize_method: str = "LANCZOS",
    ) -> Image.Image:
        cw, ch = content_size
        sw, sh = source.width, source.height
        if (sw, sh) == (cw, ch):
            return source
        if sw > cw or sh > ch:
            fit_r = min(cw / max(1, sw), ch / max(1, sh))
            sw = max(1, int(sw * fit_r))
            sh = max(1, int(sh * fit_r))
            source = resample_image(
                source,
                (sw, sh),
                resize_method,
                is_interactive_render=False,
            )
        canvas = Image.new("RGBA", (cw, ch), fill_rgba or (0, 0, 0, 255))
        ox = (cw - sw) // 2
        oy = (ch - sh) // 2
        canvas.alpha_composite(source.convert("RGBA"), (ox, oy))
        return canvas

    def render(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        if self._gpu_export_service is None:
            raise RuntimeError("GPU export service is not configured")
        result = self._render_gpu(snap, request)
        self._last_backend = result.backend
        self._last_debug = result.debug
        return result

    def _render_gpu(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        prepared = self.prepare_canvas_frame(snap, request)
        return self._render_prepared(prepared, request)

    def _resolve_images(self, snap, request: VideoRenderRequest):
        img1 = self._image_loader(snap.image1_path, request.auto_crop)
        img2 = self._image_loader(snap.image2_path, request.auto_crop)
        if not img1:
            img1 = Image.new(
                "RGBA",
                (
                    max(1, request.target_surface.width),
                    max(1, request.target_surface.height),
                ),
                (50, 50, 50, 255),
            )
        if not img2:
            img2 = Image.new(
                "RGBA",
                (
                    max(1, request.target_surface.width),
                    max(1, request.target_surface.height),
                ),
                (80, 80, 80, 255),
            )
        return img1, img2

    def prepare_canvas_frame(self, snap, request: VideoRenderRequest) -> PreparedCanvasFrame:
        debug = {}
        resize_method = get_effective_export_interpolation_method(snap.viewport_state)
        prescale_target = self._resolve_prescale_target(request)
        cache_key = (
            snap.image1_path,
            snap.image2_path,
            prescale_target[0],
            prescale_target[1],
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
            img1, img2 = prescale_pair(
                img1,
                img2,
                prescale_target[0],
                prescale_target[1],
                resize_method,
            )
            debug["prescale_ms"] = (time.perf_counter() - prescale_started) * 1000.0
            self._prescaled_cache = (cache_key, img1, img2)

        debug["prescale_target_width"] = float(prescale_target[0])
        debug["prescale_target_height"] = float(prescale_target[1])
        scaled_global_bounds = request.global_bounds
        if request.global_bounds is not None:
            scaled_global_bounds = self._scale_global_bounds(
                request.global_bounds,
                prescale_target,
                output_size=(
                    request.target_surface.width,
                    request.target_surface.height,
                ),
            )
            if scaled_global_bounds is not request.global_bounds:
                debug["scaled_bounds_base_width"] = float(scaled_global_bounds.base_width)
                debug["scaled_bounds_base_height"] = float(scaled_global_bounds.base_height)
                debug["scaled_bounds_pad_left"] = float(scaled_global_bounds.pad_left)
            debug["scaled_bounds_pad_right"] = float(scaled_global_bounds.pad_right)
            debug["scaled_bounds_pad_top"] = float(scaled_global_bounds.pad_top)
            debug["scaled_bounds_pad_bottom"] = float(scaled_global_bounds.pad_bottom)
        return self._prepare_canvas_frame_core(
            snap,
            request,
            img1,
            img2,
            scaled_global_bounds=scaled_global_bounds,
            debug=debug,
            allow_feature_layout_fallback=False,
        )

    def prepare_canvas_frame_from_images(
        self,
        snap,
        request: VideoRenderRequest,
        image1: Image.Image,
        image2: Image.Image,
        *,
        allow_feature_layout_fallback: bool = False,
        normalize_snapshot: bool = True,
    ) -> PreparedCanvasFrame:
        debug = {
            "load_ms": 0.0,
            "prescale_ms": 0.0,
            "prescale_target_width": float(image1.width),
            "prescale_target_height": float(image1.height),
        }
        return self._prepare_canvas_frame_core(
            snap,
            request,
            image1,
            image2,
            scaled_global_bounds=request.global_bounds,
            debug=debug,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            normalize_snapshot=normalize_snapshot,
        )

    def _prepare_canvas_frame_core(self, *_args, **_kwargs) -> PreparedCanvasFrame:
        raise NotImplementedError

    def _render_prepared(
        self, prepared: PreparedCanvasFrame, request: VideoRenderRequest
    ) -> RenderedFrame:
        debug = dict(prepared.debug)
        gpu_render_started = time.perf_counter()
        diff_image = None
        try:
            render_cache = getattr(
                getattr(prepared.store, "viewport", None),
                "session_data",
                None,
            )
            render_cache = getattr(render_cache, "render_cache", None)
            diff_image = getattr(render_cache, "cached_diff_image", None)
        except Exception:
            diff_image = None
        frame_pil, gpu_debug = self._gpu_export_service.render_plan(
            prepared.plan,
            diff_image=diff_image,
        )
        debug["gpu_render_ms"] = (time.perf_counter() - gpu_render_started) * 1000.0
        debug.update(gpu_debug)
        if frame_pil is None:
            return RenderedFrame(
                image=Image.new(
                    "RGBA",
                    (
                        request.target_surface.width,
                        request.target_surface.height,
                    ),
                    request.target_surface.fill_rgba,
                ),
                backend="gpu",
                debug=debug,
            )

        composite_started = time.perf_counter()
        if frame_pil.size == (
            max(1, int(getattr(prepared.plan, "canvas_w", 0) or 0)),
            max(1, int(getattr(prepared.plan, "canvas_h", 0) or 0)),
        ):
            debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
            return RenderedFrame(image=frame_pil, backend="gpu", debug=debug)
        if frame_pil.size == (
            request.target_surface.width,
            request.target_surface.height,
        ):
            debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
            return RenderedFrame(image=frame_pil, backend="gpu", debug=debug)

        final_frame = Image.new(
            "RGBA",
            (
                request.target_surface.width,
                request.target_surface.height,
            ),
            prepared.fill_rgba,
        )
        final_frame.alpha_composite(frame_pil, (prepared.image_dest_x, prepared.image_dest_y))
        debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
        return RenderedFrame(image=final_frame, backend="gpu", debug=debug)

    def render_from_images(
        self,
        snap,
        request: VideoRenderRequest,
        image1: Image.Image,
        image2: Image.Image,
        *,
        allow_feature_layout_fallback: bool = False,
        normalize_snapshot: bool = True,
    ) -> RenderedFrame:
        prepared = self.prepare_canvas_frame_from_images(
            snap,
            request,
            image1,
            image2,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            normalize_snapshot=normalize_snapshot,
        )
        result = self._render_prepared(prepared, request)
        self._last_backend = result.backend
        self._last_debug = result.debug
        return result

    @staticmethod
    def _scale_global_bounds(
        bounds: GlobalCanvasBounds,
        prescale_target: tuple[int, int],
        *,
        output_size: tuple[int, int] | None = None,
    ) -> GlobalCanvasBounds:
        source_w = max(1, int(bounds.base_width))
        source_h = max(1, int(bounds.base_height))
        target_w, target_h = prescale_target
        ratio = min(float(target_w) / float(source_w), float(target_h) / float(source_h))
        if output_size is not None:
            out_w, out_h = output_size
            span_x = max(1.0, float(bounds.canvas_x_max) - float(bounds.canvas_x_min))
            span_y = max(1.0, float(bounds.canvas_y_max) - float(bounds.canvas_y_min))
            min_ratio = min(
                1.0,
                float(max(1, out_w)) / (float(source_w) * span_x),
                float(max(1, out_h)) / (float(source_h) * span_y),
            )
            ratio = max(ratio, min_ratio)
        if abs(ratio - 1.0) < 1e-9:
            return bounds
        return GlobalCanvasBounds(
            pad_left=int(round(float(bounds.pad_left) * ratio)),
            pad_right=int(round(float(bounds.pad_right) * ratio)),
            pad_top=int(round(float(bounds.pad_top) * ratio)),
            pad_bottom=int(round(float(bounds.pad_bottom) * ratio)),
            base_width=max(1, int(round(float(bounds.base_width) * ratio))),
            base_height=max(1, int(round(float(bounds.base_height) * ratio))),
            canvas_x_min=float(bounds.canvas_x_min),
            canvas_x_max=float(bounds.canvas_x_max),
            canvas_y_min=float(bounds.canvas_y_min),
            canvas_y_max=float(bounds.canvas_y_max),
        )


def _create_tab_snapshot_renderer(*args, **kwargs):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    return registry.create_service("snapshot_frame_renderer", *args, **kwargs)
