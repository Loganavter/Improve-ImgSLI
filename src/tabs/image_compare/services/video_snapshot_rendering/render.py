"""GPU render of a prepared snapshot frame."""

from __future__ import annotations

import time

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    RenderedFrame,
    VideoRenderRequest,
)
from tabs.image_compare.services.video_snapshot_rendering.models import PreparedCanvasFrame


def _extract_diff_image(prepared: PreparedCanvasFrame):
    try:
        render_cache = getattr(
            getattr(prepared.store, "viewport", None),
            "session_data",
            None,
        )
        render_cache = getattr(render_cache, "render_cache", None)
        return getattr(render_cache, "cached_diff_image", None)
    except Exception:
        return None


def _finish_rendered_frame(
    frame_pil,
    gpu_debug: dict,
    debug: dict,
    prepared: PreparedCanvasFrame,
    request: VideoRenderRequest,
) -> RenderedFrame:
    debug = dict(debug)
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
    final_frame.alpha_composite(
        frame_pil, (prepared.image_dest_x, prepared.image_dest_y)
    )
    debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
    return RenderedFrame(image=final_frame, backend="gpu", debug=debug)


def render_prepared(
    gpu_export_service,
    prepared: PreparedCanvasFrame,
    request: VideoRenderRequest,
) -> RenderedFrame:
    debug = dict(prepared.debug)
    gpu_render_started = time.perf_counter()
    diff_image = _extract_diff_image(prepared)
    frame_pil, gpu_debug = gpu_export_service.render_plan(
        prepared.plan,
        diff_image=diff_image,
    )
    debug["gpu_render_ms"] = (time.perf_counter() - gpu_render_started) * 1000.0
    return _finish_rendered_frame(frame_pil, gpu_debug, debug, prepared, request)


def render_prepared_async(
    gpu_export_service,
    prepared: PreparedCanvasFrame,
    request: VideoRenderRequest,
    callback,
) -> None:
    """Non-blocking counterpart to :func:`render_prepared`.

    Submits the GPU render and returns immediately; ``callback(RenderedFrame)``
    fires later, on the main thread. ``prepared`` (the CPU-side image
    loading/caching work) must already be done by the caller — only the GPU
    step is deferred.
    """
    debug = dict(prepared.debug)
    gpu_render_started = time.perf_counter()
    diff_image = _extract_diff_image(prepared)

    def _on_gpu_done(frame_pil, gpu_debug, error):
        if error is not None:
            callback(_finish_rendered_frame(None, {}, debug, prepared, request))
            return
        debug["gpu_render_ms"] = (time.perf_counter() - gpu_render_started) * 1000.0
        callback(
            _finish_rendered_frame(frame_pil, gpu_debug or {}, debug, prepared, request)
        )

    gpu_export_service.render_plan_async(
        prepared.plan,
        diff_image=diff_image,
        callback=_on_gpu_done,
    )
