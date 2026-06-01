from __future__ import annotations

import time
from dataclasses import dataclass

from PIL import Image

from core.tracing import Tracer
from shared.image_processing.prescale import prescale_pair
from shared.image_processing.resize import resample_image

from plugins.export.services.snapshot_render_plan_builder import SnapshotRenderPlanBuilder
from ui.canvas_presentation.models import CanvasTarget
from ui.canvas_presentation.layout import compute_content_layout
from ui.canvas_presentation.plan_builder import CanvasGeometry
from shared.rendering import get_effective_export_interpolation_method
from plugins.video_editor.services.video_export_models import RenderedFrame, VideoRenderRequest
from plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from ui.canvas_presentation import build_render_frame_presentation, build_snapshot_store_presentation

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
    def __init__(self, image_loader, gpu_export_service=None) -> None:
        self._image_loader = image_loader
        self._gpu_export_service = gpu_export_service
        self._last_backend = "gpu"
        self._last_debug: dict = {}
        self._prescaled_cache: tuple | None = None
        self._image_prep_cache: tuple | None = None
        self._scene_images_cache: dict = {}

    @property
    def last_backend(self) -> str:
        return self._last_backend

    def reset_backend_state(self) -> None:
        self._last_backend = "gpu"
        self._prescaled_cache = None
        self._image_prep_cache = None
        self._scene_images_cache = {}

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

    @staticmethod
    def _resolve_scaled_content_geometry(frame) -> tuple[tuple[int, int], tuple[int, int], int, int]:
        if frame.virtual_layout is None:
            return (
                (frame.render_width, frame.render_height),
                (frame.render_width, frame.render_height),
                0,
                0,
            )

        bounds = frame.virtual_layout.canvas_bounds
        span_x = max(1e-6, float(bounds.x_max - bounds.x_min))
        span_y = max(1e-6, float(bounds.y_max - bounds.y_min))
        base_w = max(1, int(round(frame.render_width / span_x)))
        base_h = max(1, int(round(frame.render_height / span_y)))
        pad_left = max(0, int(round(-float(bounds.x_min) * base_w)))
        pad_top = max(0, int(round(-float(bounds.y_min) * base_h)))
        return (
            (frame.render_width, frame.render_height),
            (base_w, base_h),
            pad_left,
            pad_top,
        )

    @staticmethod
    def _image_prep_cache_key(
        img1,
        img2,
        request,
        scaled_global_bounds,
        resize_method,
        normalize_snapshot,
    ):
        bounds_key = None
        if scaled_global_bounds is not None:
            bounds_key = (
                int(scaled_global_bounds.pad_left),
                int(scaled_global_bounds.pad_right),
                int(scaled_global_bounds.pad_top),
                int(scaled_global_bounds.pad_bottom),
                int(scaled_global_bounds.base_width),
                int(scaled_global_bounds.base_height),
            )
        return (
            id(img1), id(img2),
            img1.size if img1 else None,
            img2.size if img2 else None,
            request.fit_content,
            bounds_key,
            request.target_surface.fill_rgba,
            resize_method,
            request.target_surface.width,
            request.target_surface.height,
            bool(normalize_snapshot),
        )

    @staticmethod
    def _rebuild_snapshot_store(
        snap,
        c,
        fit_content,
        scaled_global_bounds,
        normalize_snapshot_store_enabled,
    ):
        from core.store import ImageItem, Store
        from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

        store = Store()
        store.viewport = snap.viewport_state.clone()
        store.settings = snap.settings_state.freeze_for_export()
        store.runtime_cache.overlay_clip_rect = None

        normalize_snapshot = get_canvas_feature_command_by_alias("overlay.snapshot_normalize")
        if (
            normalize_snapshot_store_enabled
            and normalize_snapshot is not None
            and not (fit_content and scaled_global_bounds is not None)
        ):
            normalize_snapshot(store)

        store.viewport.session_data.image_state.image1 = c["display_img1"]
        store.viewport.session_data.image_state.image2 = c["display_img2"]
        store.document.image1_path = getattr(snap, "image1_path", None)
        store.document.image2_path = getattr(snap, "image2_path", None)
        store.document.image_list1 = [
            ImageItem(
                image=c["source_img1"],
                path=getattr(snap, "image1_path", None) or "",
                display_name=getattr(snap, "name1", None) or "",
            )
        ]
        store.document.image_list2 = [
            ImageItem(
                image=c["source_img2"],
                path=getattr(snap, "image2_path", None) or "",
                display_name=getattr(snap, "name2", None) or "",
            )
        ]
        store.document.current_index1 = 0 if store.document.image_list1 else -1
        store.document.current_index2 = 0 if store.document.image_list2 else -1
        store.document.original_image1 = c["source_img1"]
        store.document.original_image2 = c["source_img2"]
        store.document.full_res_image1 = c["source_img1"]
        store.document.full_res_image2 = c["source_img2"]
        store.viewport.interaction_state.is_interactive_mode = False
        store.viewport.geometry_state.pixmap_width = c["render_w"]
        store.viewport.geometry_state.pixmap_height = c["render_h"]

        if fit_content and scaled_global_bounds is not None:
            apply_virtual_layout = get_canvas_feature_command_by_alias(
                "overlay.snapshot_apply_virtual_layout"
            )
            if apply_virtual_layout is not None:
                apply_virtual_layout(
                    store,
                    base_w=int(scaled_global_bounds.base_width),
                    base_h=int(scaled_global_bounds.base_height),
                    virtual_layout=scaled_global_bounds.to_virtual_layout(),
                )

        return store

    def _prepare_canvas_frame_core(
        self,
        snap,
        request: VideoRenderRequest,
        img1,
        img2,
        *,
        scaled_global_bounds=None,
        debug: dict | None = None,
        allow_feature_layout_fallback: bool = False,
        normalize_snapshot: bool = True,
    ) -> PreparedCanvasFrame:
        debug = {} if debug is None else debug
        resize_method = get_effective_export_interpolation_method(snap.viewport_state)

        image_prep_key = self._image_prep_cache_key(
            img1,
            img2,
            request,
            scaled_global_bounds,
            resize_method,
            normalize_snapshot,
        )
        cached = self._image_prep_cache
        if cached is not None and cached[0] == image_prep_key:
            c = cached[1]
            debug["build_store_ms"] = 0.0
            debug["pair_resize_method"] = resize_method
            debug["image_prep_cache"] = "hit"

            store = self._rebuild_snapshot_store(
                snap,
                c,
                request.fit_content,
                scaled_global_bounds,
                normalize_snapshot,
            )

            layout_started = time.perf_counter()
            plan = SnapshotRenderPlanBuilder(store).build_render_plan(
                c["scaled_source1"],
                c["scaled_source2"],
                source_image1=c["scaled_source1"],
                source_image2=c["scaled_source2"],
                source_key=(
                    c["source_key"],
                    c["target_size"],
                    c["content_size"],
                    c["pad_left"],
                    c["pad_top"],
                ),
                display_cache_key=(
                    c["display_cache_key"],
                    c["target_size"],
                ),
                target_surface=request.target_surface,
                canvas_fill_rgba=request.target_surface.fill_rgba,
                canvas_geometry=c["canvas_geometry"],
                allow_feature_layout_fallback=allow_feature_layout_fallback,
                scene_images_cache=self._scene_images_cache,
            )
            debug["plan_build_ms"] = (time.perf_counter() - layout_started) * 1000.0
            debug["frame_canvas_width"] = float(c["target_size"][0])
            debug["frame_canvas_height"] = float(c["target_size"][1])
            debug["frame_content_width"] = float(c["content_size"][0])
            debug["frame_content_height"] = float(c["content_size"][1])
            debug["frame_content_x"] = float(c["output_layout"].content_x)
            debug["frame_content_y"] = float(c["output_layout"].content_y)
            debug["frame_pad_left"] = float(c["canvas_geometry"].padding_left)
            debug["frame_pad_right"] = float(c["canvas_geometry"].padding_right)
            debug["frame_pad_top"] = float(c["canvas_geometry"].padding_top)
            debug["frame_pad_bottom"] = float(c["canvas_geometry"].padding_bottom)
            return PreparedCanvasFrame(
                store=store,
                plan=plan,
                output_width=request.target_surface.width,
                output_height=request.target_surface.height,
                image_dest_x=c["output_layout"].content_x,
                image_dest_y=c["output_layout"].content_y,
                fill_rgba=request.target_surface.fill_rgba,
                debug=debug,
            )

        debug["image_prep_cache"] = "miss"
        build_store_started = time.perf_counter()
        presentation = build_snapshot_store_presentation(
            snap,
            img1,
            img2,
            fit_content=request.fit_content,
            global_bounds=scaled_global_bounds,
            fill_color=request.target_surface.fill_rgba,
            resize_method=resize_method,
            normalize_snapshot=normalize_snapshot,
        )
        debug["build_store_ms"] = (time.perf_counter() - build_store_started) * 1000.0
        debug["pair_resize_method"] = resize_method
        if request.fit_content and request.global_bounds is not None:
            debug["global_bounds_pad_left"] = float(request.global_bounds.pad_left)
            debug["global_bounds_pad_right"] = float(request.global_bounds.pad_right)
            debug["global_bounds_pad_top"] = float(request.global_bounds.pad_top)
            debug["global_bounds_pad_bottom"] = float(request.global_bounds.pad_bottom)

        layout_started = time.perf_counter()
        target = CanvasTarget(
            width=max(1, int(request.target_surface.width)),
            height=max(1, int(request.target_surface.height)),
            fill_rgba=request.target_surface.fill_rgba,
        )
        output_layout = compute_content_layout(
            target,
            image_width=presentation.display_image1.width,
            image_height=presentation.display_image1.height,
        )
        frame = build_render_frame_presentation(
            presentation,
            target=target,
        )
        target_size, content_size, pad_left, pad_top = self._resolve_scaled_content_geometry(frame)
        _src1_sz = (presentation.source_image1.width, presentation.source_image1.height) if presentation.source_image1 else None
        _src2_sz = (presentation.source_image2.width, presentation.source_image2.height) if presentation.source_image2 else None
        _disp1_sz = (presentation.display_image1.width, presentation.display_image1.height) if presentation.display_image1 else None
        self._trace(
            "video.render.layout",
            f"layout target={target_size[0]}x{target_size[1]} content={content_size[0]}x{content_size[1]}",
            {
                "target_surface": (
                    int(request.target_surface.width),
                    int(request.target_surface.height),
                ),
                "source1_size": _src1_sz,
                "source2_size": _src2_sz,
                "display1_size": _disp1_sz,
                "target_size": tuple(int(v) for v in target_size),
                "content_size": tuple(int(v) for v in content_size),
                "pad_left": int(pad_left),
                "pad_top": int(pad_top),
                "fit_content": bool(request.fit_content),
                "global_bounds": repr(request.global_bounds),
                "scaled_global_bounds": repr(scaled_global_bounds),
                "resize_method": resize_method,
            },
        )
        canvas_geometry = CanvasGeometry(
            image_width=max(1, int(content_size[0])),
            image_height=max(1, int(content_size[1])),
            canvas_width=max(1, int(target_size[0])),
            canvas_height=max(1, int(target_size[1])),
            padding_left=max(0, int(pad_left)),
            padding_top=max(0, int(pad_top)),
            padding_right=max(0, int(target_size[0] - content_size[0] - pad_left)),
            padding_bottom=max(0, int(target_size[1] - content_size[1] - pad_top)),
            virtual_layout=frame.virtual_layout,
        )
        scaled_source1 = self._fit_source_to_content(
            presentation.source_image1,
            content_size,
            request.target_surface.fill_rgba,
            resize_method,
        )
        scaled_source2 = self._fit_source_to_content(
            presentation.source_image2,
            content_size,
            request.target_surface.fill_rgba,
            resize_method,
        )

        self._image_prep_cache = (image_prep_key, {
            "display_img1": presentation.display_image1,
            "display_img2": presentation.display_image2,
            "source_img1": presentation.source_image1,
            "source_img2": presentation.source_image2,
            "source_key": presentation.images.source_key,
            "display_cache_key": presentation.images.display_cache_key,
            "scaled_source1": scaled_source1,
            "scaled_source2": scaled_source2,
            "canvas_geometry": canvas_geometry,
            "output_layout": output_layout,
            "target_size": target_size,
            "content_size": content_size,
            "pad_left": pad_left,
            "pad_top": pad_top,
            "render_w": frame.render_width,
            "render_h": frame.render_height,
        })

        plan = SnapshotRenderPlanBuilder(frame.store).build_render_plan(
            scaled_source1,
            scaled_source2,
            source_image1=scaled_source1,
            source_image2=scaled_source2,
            source_key=(
                frame.source_key,
                target_size,
                content_size,
                pad_left,
                pad_top,
            ),
            display_cache_key=(
                presentation.display_cache_key,
                target_size,
            ),
            target_surface=request.target_surface,
            canvas_fill_rgba=request.target_surface.fill_rgba,
            canvas_geometry=canvas_geometry,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            scene_images_cache=self._scene_images_cache,
        )
        self._trace(
            "video.render.plan",
            f"plan canvas={getattr(plan, 'canvas_w', 0)}x{getattr(plan, 'canvas_h', 0)}",
            {
                "plan_canvas": (
                    int(getattr(plan, "canvas_w", 0) or 0),
                    int(getattr(plan, "canvas_h", 0) or 0),
                ),
                "plan_image1_size": getattr(getattr(plan, "image1", None), "size", None),
                "plan_image2_size": getattr(getattr(plan, "image2", None), "size", None),
                "display_cache_key": repr(getattr(plan, "display_cache_key", None)),
                "gl_zoom_interpolation": getattr(
                    getattr(plan, "gl_scene", None),
                    "zoom_interpolation_method",
                    None,
                ),
                "gl_diff_mode": getattr(getattr(plan, "gl_scene", None), "diff_mode_int", None),
                "overlay_clip_rect": getattr(
                    getattr(plan, "gl_scene", None),
                    "overlay_clip_rect",
                    None,
                ),
            },
        )
        debug["plan_build_ms"] = (time.perf_counter() - layout_started) * 1000.0
        debug["frame_canvas_width"] = float(target_size[0])
        debug["frame_canvas_height"] = float(target_size[1])
        debug["frame_content_width"] = float(content_size[0])
        debug["frame_content_height"] = float(content_size[1])
        debug["frame_content_x"] = float(output_layout.content_x)
        debug["frame_content_y"] = float(output_layout.content_y)
        debug["frame_pad_left"] = float(canvas_geometry.padding_left)
        debug["frame_pad_right"] = float(canvas_geometry.padding_right)
        debug["frame_pad_top"] = float(canvas_geometry.padding_top)
        debug["frame_pad_bottom"] = float(canvas_geometry.padding_bottom)
        return PreparedCanvasFrame(
            store=frame.store,
            plan=plan,
            output_width=request.target_surface.width,
            output_height=request.target_surface.height,
            image_dest_x=output_layout.content_x,
            image_dest_y=output_layout.content_y,
            fill_rgba=request.target_surface.fill_rgba,
            debug=debug,
        )

    def prepare_canvas_frame(self, snap, request: VideoRenderRequest) -> PreparedCanvasFrame:
        debug = {}
        resize_method = get_effective_export_interpolation_method(snap.viewport_state)
        prescale_target = self._resolve_prescale_target(request)
        self._trace(
            "video.render.prescale.begin",
            f"prescale target={prescale_target[0]}x{prescale_target[1]}",
            {
                "target_surface": (
                    int(request.target_surface.width),
                    int(request.target_surface.height),
                ),
                "prescale_target": tuple(int(v) for v in prescale_target),
                "resize_method": resize_method,
                "fit_content": bool(request.fit_content),
                "global_bounds": repr(request.global_bounds),
            },
        )
        cache_key = (
            snap.image1_path, snap.image2_path,
            prescale_target[0], prescale_target[1],
        )
        if self._prescaled_cache is not None and self._prescaled_cache[0] == cache_key:
            img1, img2 = self._prescaled_cache[1], self._prescaled_cache[2]
            debug["load_ms"] = 0.0
            debug["prescale_ms"] = 0.0
            self._trace(
                "video.render.prescale.cache",
                f"prescale cache result={getattr(img1, 'size', None)}",
                {
                    "result_sizes": (
                        getattr(img1, "size", None),
                        getattr(img2, "size", None),
                    ),
                    "prescale_target": tuple(int(v) for v in prescale_target),
                    "resize_method": resize_method,
                },
            )
        else:
            started = time.perf_counter()
            img1, img2 = self._resolve_images(snap, request)
            debug["load_ms"] = (time.perf_counter() - started) * 1000.0

            prescale_started = time.perf_counter()
            original_sizes = (
                getattr(img1, "size", None),
                getattr(img2, "size", None),
            )
            img1, img2 = prescale_pair(
                img1,
                img2,
                prescale_target[0],
                prescale_target[1],
                resize_method,
            )
            debug["prescale_ms"] = (time.perf_counter() - prescale_started) * 1000.0
            self._prescaled_cache = (cache_key, img1, img2)
            self._trace(
                "video.render.prescale.end",
                f"prescaled {getattr(img1, 'size', None)} / {getattr(img2, 'size', None)}",
                {
                    "cache": "miss",
                    "original_sizes": original_sizes,
                    "result_sizes": (
                        getattr(img1, "size", None),
                        getattr(img2, "size", None),
                    ),
                    "prescale_ms": debug["prescale_ms"],
                    "prescale_target": tuple(int(v) for v in prescale_target),
                    "resize_method": resize_method,
                },
            )
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

    def _render_prepared(self, prepared: PreparedCanvasFrame, request: VideoRenderRequest) -> RenderedFrame:
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
        if ratio >= 0.999:
            return bounds

        scaled = GlobalCanvasBounds(
            pad_left=max(0, int(round(bounds.pad_left * ratio))),
            pad_right=max(0, int(round(bounds.pad_right * ratio))),
            pad_top=max(0, int(round(bounds.pad_top * ratio))),
            pad_bottom=max(0, int(round(bounds.pad_bottom * ratio))),
            base_width=max(1, int(round(source_w * ratio))),
            base_height=max(1, int(round(source_h * ratio))),
            canvas_x_min=float(bounds.canvas_x_min),
            canvas_x_max=float(bounds.canvas_x_max),
            canvas_y_min=float(bounds.canvas_y_min),
            canvas_y_max=float(bounds.canvas_y_max),
        )
        return scaled

    def _render_gpu(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        prepared = self.prepare_canvas_frame(snap, request)
        return self._render_prepared(prepared, request)
