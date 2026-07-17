"""Render-plan construction and debug metrics for prepared frames."""

from __future__ import annotations

import time

from tabs.image_compare.services.snapshot_render_plan_builder import (
    SnapshotRenderPlanBuilder,
)
from tabs.image_compare.services.video_snapshot_rendering.models import (
    ImagePrepCacheEntry,
    PreparedCanvasFrame,
)


def fill_frame_debug(
    debug: dict,
    *,
    target_size: tuple[int, int],
    content_size: tuple[int, int],
    content_x: float,
    content_y: float,
    canvas_geometry,
    plan_build_started: float,
) -> None:
    debug["plan_build_ms"] = (time.perf_counter() - plan_build_started) * 1000.0
    debug["frame_canvas_width"] = float(target_size[0])
    debug["frame_canvas_height"] = float(target_size[1])
    debug["frame_content_width"] = float(content_size[0])
    debug["frame_content_height"] = float(content_size[1])
    debug["frame_content_x"] = float(content_x)
    debug["frame_content_y"] = float(content_y)
    debug["frame_pad_left"] = float(canvas_geometry.padding_left)
    debug["frame_pad_right"] = float(canvas_geometry.padding_right)
    debug["frame_pad_top"] = float(canvas_geometry.padding_top)
    debug["frame_pad_bottom"] = float(canvas_geometry.padding_bottom)


def build_plan_from_entry(
    store,
    entry: ImagePrepCacheEntry,
    request,
    *,
    allow_feature_layout_fallback: bool,
    scene_images_cache: dict,
):
    return SnapshotRenderPlanBuilder(store).build_render_plan(
        entry.scaled_source1,
        entry.scaled_source2,
        source_image1=entry.scaled_source1,
        source_image2=entry.scaled_source2,
        source_key=(
            entry.source_key,
            entry.target_size,
            entry.content_size,
            entry.pad_left,
            entry.pad_top,
        ),
        display_cache_key=(
            entry.display_cache_key,
            entry.target_size,
        ),
        target_surface=request.target_surface,
        canvas_fill_rgba=request.target_surface.fill_rgba,
        canvas_geometry=entry.canvas_geometry,
        allow_feature_layout_fallback=allow_feature_layout_fallback,
        scene_images_cache=scene_images_cache,
    )


def prepared_from_entry(
    store,
    plan,
    entry: ImagePrepCacheEntry,
    request,
    debug: dict,
) -> PreparedCanvasFrame:
    return PreparedCanvasFrame(
        store=store,
        plan=plan,
        output_width=request.target_surface.width,
        output_height=request.target_surface.height,
        image_dest_x=entry.output_layout.content_x,
        image_dest_y=entry.output_layout.content_y,
        fill_rgba=request.target_surface.fill_rgba,
        debug=debug,
    )


def trace_plan(trace, plan) -> None:
    if trace is None:
        return
    trace(
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
            "qrhi_zoom_interpolation": getattr(
                getattr(plan, "render_scene", None),
                "zoom_interpolation_method",
                None,
            ),
            "qrhi_diff_mode": getattr(
                getattr(plan, "render_scene", None), "diff_mode_int", None
            ),
            "overlay_clip_rect": getattr(
                getattr(plan, "render_scene", None),
                "overlay_clip_rect",
                None,
            ),
        },
    )
