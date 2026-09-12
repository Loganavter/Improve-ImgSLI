"""GPU render of a prepared snapshot frame."""

from __future__ import annotations

import time

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    RenderedFrame,
    VideoRenderRequest,
)
from tabs.image_compare.services.video_snapshot_rendering.models import PreparedCanvasFrame


def render_prepared(
    gpu_export_service,
    prepared: PreparedCanvasFrame,
    request: VideoRenderRequest,
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
    frame_pil, gpu_debug = gpu_export_service.render_plan(
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
    final_frame.alpha_composite(
        frame_pil, (prepared.image_dest_x, prepared.image_dest_y)
    )
    debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
    return RenderedFrame(image=final_frame, backend="gpu", debug=debug)
