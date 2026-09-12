"""Prepare orchestration: load/prescale → core hit/miss."""

from __future__ import annotations

import time

from PIL import Image

from shared.image_processing.prescale import prescale_pair
from shared.rendering import get_effective_export_interpolation_method
from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    VideoRenderRequest,
)
from tabs.image_compare.services.video_snapshot_rendering.caches import FrameRenderCaches
from tabs.image_compare.services.video_snapshot_rendering.geometry import (
    resolve_prescale_target,
    scale_global_bounds,
)
from tabs.image_compare.services.video_snapshot_rendering.images import resolve_images
from tabs.image_compare.services.video_snapshot_rendering.models import PreparedCanvasFrame
from tabs.image_compare.services.video_snapshot_rendering.prepare_hit import (
    prepare_from_cache_hit,
)
from tabs.image_compare.services.video_snapshot_rendering.prepare_miss import (
    prepare_from_cache_miss,
)


def prepare_canvas_frame_core(
    image_loader,
    caches: FrameRenderCaches,
    snap,
    request: VideoRenderRequest,
    img1,
    img2,
    *,
    scaled_global_bounds=None,
    debug: dict | None = None,
    allow_feature_layout_fallback: bool = False,
    normalize_snapshot: bool = True,
    trace=None,
) -> PreparedCanvasFrame:
    debug = {} if debug is None else debug
    resize_method = get_effective_export_interpolation_method(snap.viewport_state)

    image_prep_key = FrameRenderCaches.image_prep_key(
        img1,
        img2,
        request,
        scaled_global_bounds,
        resize_method,
        normalize_snapshot,
    )
    cached = caches.image_prep
    if cached is not None and cached[0] == image_prep_key:
        return prepare_from_cache_hit(
            snap,
            request,
            cached[1],
            scaled_global_bounds=scaled_global_bounds,
            resize_method=resize_method,
            normalize_snapshot=normalize_snapshot,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            scene_images_cache=caches.scene_images,
            debug=debug,
        )

    return prepare_from_cache_miss(
        snap,
        request,
        img1,
        img2,
        image_prep_key=image_prep_key,
        scaled_global_bounds=scaled_global_bounds,
        resize_method=resize_method,
        normalize_snapshot=normalize_snapshot,
        allow_feature_layout_fallback=allow_feature_layout_fallback,
        caches=caches,
        debug=debug,
        trace=trace,
    )


def prepare_canvas_frame(
    image_loader,
    caches: FrameRenderCaches,
    snap,
    request: VideoRenderRequest,
    *,
    trace=None,
) -> PreparedCanvasFrame:
    debug = {}
    resize_method = get_effective_export_interpolation_method(snap.viewport_state)
    prescale_target = resolve_prescale_target(request)
    if trace is not None:
        trace(
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
        snap.image1_path,
        snap.image2_path,
        prescale_target[0],
        prescale_target[1],
    )
    if caches.prescaled is not None and caches.prescaled[0] == cache_key:
        img1, img2 = caches.prescaled[1], caches.prescaled[2]
        debug["load_ms"] = 0.0
        debug["prescale_ms"] = 0.0
        if trace is not None:
            trace(
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
        img1, img2 = resolve_images(image_loader, snap, request)
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
        caches.prescaled = (cache_key, img1, img2)
        if trace is not None:
            trace(
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
        scaled_global_bounds = scale_global_bounds(
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
    return prepare_canvas_frame_core(
        image_loader,
        caches,
        snap,
        request,
        img1,
        img2,
        scaled_global_bounds=scaled_global_bounds,
        debug=debug,
        allow_feature_layout_fallback=False,
        trace=trace,
    )


def prepare_canvas_frame_from_images(
    image_loader,
    caches: FrameRenderCaches,
    snap,
    request: VideoRenderRequest,
    image1: Image.Image,
    image2: Image.Image,
    *,
    allow_feature_layout_fallback: bool = False,
    normalize_snapshot: bool = True,
    trace=None,
) -> PreparedCanvasFrame:
    debug = {
        "load_ms": 0.0,
        "prescale_ms": 0.0,
        "prescale_target_width": float(image1.width),
        "prescale_target_height": float(image1.height),
    }
    return prepare_canvas_frame_core(
        image_loader,
        caches,
        snap,
        request,
        image1,
        image2,
        scaled_global_bounds=request.global_bounds,
        debug=debug,
        allow_feature_layout_fallback=allow_feature_layout_fallback,
        normalize_snapshot=normalize_snapshot,
        trace=trace,
    )
