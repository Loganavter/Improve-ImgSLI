"""Cache-hit prepare path for snapshot frames."""

from __future__ import annotations

import time

from tabs.image_compare.services.video_snapshot_rendering.models import (
    ImagePrepCacheEntry,
    PreparedCanvasFrame,
)
from tabs.image_compare.services.video_snapshot_rendering.plan_build import (
    build_plan_from_entry,
    fill_frame_debug,
    prepared_from_entry,
)
from tabs.image_compare.services.video_snapshot_rendering.store_rebuild import (
    rebuild_snapshot_store,
)


def prepare_from_cache_hit(
    snap,
    request,
    entry: ImagePrepCacheEntry,
    *,
    scaled_global_bounds,
    resize_method: str,
    normalize_snapshot: bool,
    allow_feature_layout_fallback: bool,
    scene_images_cache: dict,
    debug: dict,
) -> PreparedCanvasFrame:
    debug["build_store_ms"] = 0.0
    debug["pair_resize_method"] = resize_method
    debug["image_prep_cache"] = "hit"

    store = rebuild_snapshot_store(
        snap,
        entry,
        request.fit_content,
        scaled_global_bounds,
        normalize_snapshot,
    )

    layout_started = time.perf_counter()
    plan = build_plan_from_entry(
        store,
        entry,
        request,
        allow_feature_layout_fallback=allow_feature_layout_fallback,
        scene_images_cache=scene_images_cache,
    )
    fill_frame_debug(
        debug,
        target_size=entry.target_size,
        content_size=entry.content_size,
        content_x=entry.output_layout.content_x,
        content_y=entry.output_layout.content_y,
        canvas_geometry=entry.canvas_geometry,
        plan_build_started=layout_started,
    )
    return prepared_from_entry(store, plan, entry, request, debug)
