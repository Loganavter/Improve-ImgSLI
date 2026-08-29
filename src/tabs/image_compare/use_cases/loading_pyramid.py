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

from tabs.image_compare.debug import ic_preview_debug as _preview_log

logger = logging.getLogger("ImproveImgSLI")


def start_pyramid_builds(controller, *stores) -> None:
    # Called as start_pyramid_builds(controller, u1, u2) -- positional order
    # matches image_state.image1/image2 at the call site, so slot number is
    # simply the 1-based position here.
    # Prefer shared coordinator when present (B3 dedup); fallback keeps fake
    # controllers without coordinator working.
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        task_id = getattr(controller, "_unification_task_id", 0)
        for slot_offset, store in enumerate(stores):
            image_number = slot_offset + 1
            slot_toast_live = controller._pending_full_loads.get(image_number, 0) == 0  # type: ignore[union-attr]
            slot_for_coordinator = image_number if slot_toast_live else None
            # IC abort predicate: staleness via task_id
            should_abort = lambda tid=task_id: tid != getattr(controller, "_unification_task_id", tid)
            # coordinator handles skip->finish, already-in-flight, bump, worker
            coord.start_build(store, slot_id=slot_for_coordinator, should_abort=should_abort)
            # When toast was not live, coordinator would have mapped None;
            # but legacy behavior left no mapping and no bump -- coordinator already
            # respects slot_id=None (no toast). Nothing else to do.
        return
    # Legacy path (no coordinator, e.g. SimpleNamespace fakes in tests)
    from shared.image_processing import pyramid_registry
    from shared.image_processing.pyramid_pixel_store import estimate_total_levels
    from shared.rendering.image_identity import image_uid

    from tabs._shared.loading_toast import PYRAMID_START_PROGRESS

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
    coord = getattr(controller, "_pyramid_coordinator", None)
    if coord is not None:
        coord.on_level_ready(payload)
        return
    from tabs._shared.loading_toast import PYRAMID_START_PROGRESS

    uid, level_count, total_levels, complete = payload
    # Tile replacement marker: the pyramid just wrote a LOD level into the
    # store that backs the live canvas. Only `complete` drops the pick
    # signatures (preview -> store flip); intermediate levels only arm a
    # repaint, which render_flow then gates on its signatures.
    _preview_log(
        "tiles replaced: pyramid level ready (uid=%s level=%d/%d complete=%s)",
        uid,
        level_count,
        total_levels,
        complete,
    )
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
