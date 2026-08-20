"""Image pyramid builds: spawn workers, track progress, update canvas.

The pyramid provides tiled LOD (level-of-detail) for GPU rendering.
Each full-res image store gets a pyramid that builds progressively in
a background worker, emitting per-level progress signals.

Toast progress is managed via the controller's bound methods
(``controller._finish_loading_toast``, etc.) — the dependency is
one-directional: **pyramid --> toast** (see ``loading_toast.py``).
"""

from __future__ import annotations

import logging

from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")


def start_pyramid_builds(controller, *stores) -> None:
    # Called as start_pyramid_builds(controller, u1, u2) -- positional order
    # matches image_state.image1/image2 at the call site, so slot number is
    # simply the 1-based position here.
    from shared.image_processing import pyramid_registry
    from shared.image_processing.pyramid_pixel_store import estimate_total_levels
    from shared.rendering.image_identity import image_uid

    from tabs.image_compare.use_cases.loading_toast import PYRAMID_START_PROGRESS

    task_id = controller._unification_task_id
    for slot_offset, store in enumerate(stores):
        image_number = slot_offset + 1
        # A cheap preview-resolution unify races ahead of the real
        # full-res decode and can hit this same method with a trivial,
        # already-complete pyramid. Only let the toast react once the
        # slot's real decode has actually landed -- otherwise it closes
        # over stale preview data before the real progress ever starts.
        slot_toast_live = controller._pending_full_loads.get(image_number, 0) == 0
        pyramid = pyramid_registry.ensure_pyramid(store)
        if pyramid is None:
            logger.debug(
                "[Pyramid] skip build: no pyramid for store %dx%d",
                getattr(store, "width", -1),
                getattr(store, "height", -1),
            )
            if slot_toast_live:
                controller._finish_loading_toast(image_number)
            continue
        if pyramid.is_complete():
            logger.debug(
                "[Pyramid] skip build: already complete for store %dx%d "
                "(levels=%d)",
                store.width,
                store.height,
                pyramid.level_count,
            )
            if slot_toast_live:
                controller._finish_loading_toast(image_number)
            continue
        uid = image_uid(store)
        if uid in controller._pyramid_builds:
            logger.debug("[Pyramid] skip build: already in flight (uid=%s)", uid)
            continue
        controller._pyramid_builds.add(uid)
        logger.info(
            "[Pyramid] build started for store %dx%d (uid=%s)",
            store.width,
            store.height,
            uid,
        )
        total_levels = estimate_total_levels(store.width, store.height)
        if slot_toast_live:
            controller._loading_toast_uid_slot[uid] = image_number
            controller._bump_loading_toast_pyramid_started(image_number)
        worker = GenericWorker(
            controller._pyramid_build_task, pyramid, task_id, uid, total_levels
        )
        worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
        worker.signals.partial_result.connect(controller._on_pyramid_level_ready)
        worker.signals.finished.connect(
            lambda uid=uid: controller._pyramid_builds.discard(uid)
        )
        controller.thread_pool.start(worker)


def pyramid_build_task(
    controller, pyramid, task_id, uid, total_levels, progress_callback=None
):
    # A newer unification supersedes this pair; abort at the next strip.
    # Base-store closure aborts independently via pyramid validity.
    def should_abort() -> bool:
        return task_id != controller._unification_task_id

    while pyramid.build_next_level(should_abort=should_abort):
        complete = pyramid.is_complete()
        if progress_callback is not None:
            progress_callback((uid, pyramid.level_count, total_levels, complete))
    return None


def on_pyramid_level_ready(controller, payload) -> None:
    from tabs.image_compare.use_cases.loading_toast import PYRAMID_START_PROGRESS

    uid, level_count, total_levels, complete = payload
    # Only a *completed* pyramid can flip pick_display_image from the
    # preview tier to the tiled store — that's the only publish that
    # needs the pick signatures dropped. Intermediate levels just need
    # a repaint so the per-frame LOD selector can use them; a full
    # invalidation per level caused plan re-applies mid-interaction
    # (docs/dev/rendering/display-image-pipeline.md, preview→store flip).
    if complete:
        controller._invalidate_image_canvas_render_state()
    controller._schedule_image_canvas_update()
    image_number = controller._loading_toast_uid_slot.get(uid)
    if image_number is None:
        return
    if complete:
        controller._loading_toast_uid_slot.pop(uid, None)
        controller._finish_loading_toast(image_number)
    else:
        fraction = level_count / max(total_levels, 1)
        percent = PYRAMID_START_PROGRESS + int(
            fraction * (100 - PYRAMID_START_PROGRESS)
        )
        controller._set_loading_toast_progress(image_number, percent)
