"""Image loading, pyramid build, and "loading full version of image" toast
for the Multi Compare tab -- split out of ``MultiCompareController`` to keep
that class down to wiring/composition, mirroring image_compare's own
``use_cases/loading.py`` split. Every function here takes the controller as
its first argument and reads/writes its instance state
(``_loading_toasts``, ``_pyramid_builds``, ``_pyramid_toast_slot``) directly,
same calling convention as image_compare's use_cases modules.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ImproveImgSLI")

# Progress checkpoints for the "loading full version of image" toast,
# mirroring image_compare's _session_controller: 0 at the quick preview,
# DECODE_DONE_PROGRESS once the full-res decode lands, PYRAMID_START_PROGRESS
# ..100 tracking pyramid level build-out (skipped straight to done for
# stores that need no pyramid).
DECODE_DONE_PROGRESS = 20
PYRAMID_START_PROGRESS = 40


def get_toast_manager(controller):
    main_window = getattr(controller.context, "main_window", None) if controller.context else None
    toast_manager = getattr(main_window, "toast_manager", None)
    if toast_manager is None:
        logger.debug(
            "[FullImageLoad] no toast_manager available (context=%r)", controller.context
        )
    return toast_manager


def show_loading_toast(controller, slot_id: int) -> None:
    if slot_id in controller._loading_toasts:
        return
    toast_manager = get_toast_manager(controller)
    if toast_manager is None:
        return
    message = controller.translate("msg.loading_full_image_in_progress")
    try:
        controller._loading_toasts[slot_id] = toast_manager.show_toast(
            message, duration=0, progress=0
        )
    except Exception:
        logger.exception("Failed to show full-image loading toast")


def set_loading_toast_progress(controller, slot_id: int, percent: int) -> None:
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.get(slot_id)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.update_toast(
            toast_id,
            controller.translate("msg.loading_full_image_in_progress"),
            success=False,
            duration=0,
            progress=max(0, min(99, percent)),
        )
    except Exception:
        logger.exception("Failed to update full-image loading toast")


def mark_full_res_ready(controller, slot_id: int) -> None:
    set_loading_toast_progress(controller, slot_id, DECODE_DONE_PROGRESS)


def bump_loading_toast_pyramid_started(controller, slot_id: int) -> None:
    set_loading_toast_progress(controller, slot_id, PYRAMID_START_PROGRESS)


def finish_loading_toast(controller, slot_id: int) -> None:
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.pop(slot_id, None)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.update_toast(
            toast_id,
            controller.translate("msg.loading_full_image_done"),
            success=True,
            duration=2000,
            progress=100,
        )
    except Exception:
        logger.exception("Failed to complete full-image loading toast")


def dismiss_loading_toast(controller, slot_id: int) -> None:
    """Closes a slot's loading toast without the "done" success banner --
    used when the load fails or the slot vanished mid-load, as opposed to
    ``finish_loading_toast``'s success path."""
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.pop(slot_id, None)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.close_toast(toast_id)
    except Exception:
        logger.exception("Failed to dismiss full-image loading toast")


def read_image(controller, path: Path, *, slot_id: int | None = None, start_pyramid: bool = True):
    try:
        from shared.image_processing import pixel_cache_registry
        from shared.image_processing.tiled_pixel_store import TiledPixelStore

        cached = pixel_cache_registry.lookup(str(path))
        if cached is not None:
            cache_path, width, height = cached
            store = TiledPixelStore.from_embedded_cache(cache_path, width, height)
        else:
            store = TiledPixelStore.from_path(path)
        if start_pyramid:
            start_pyramid_build(controller, store, slot_id=slot_id)
        return store
    except Exception as e:
        logger.error("Failed to load %s: %s", path, e)
        return None


def start_pyramid_build(controller, store, *, slot_id: int | None = None) -> None:
    """Kicks off background mipmap-pyramid construction for a slot's
    full-res store, mirroring image_compare's
    ``_session_controller._start_pyramid_builds``. Without this, a slot
    displayed below native resolution samples the unmipmapped native
    texture directly, which aliases; the pyramid lets the per-frame LOD
    selector in ``BaseImagesPass`` pick a downsampled level instead
    (see ``docs/dev/rendering/...`` LOD selection, ``shared/rendering/lod.py``).

    ``slot_id``, when given, drives the "loading full version of image"
    toast (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up) through
    its pyramid-build stage -- every early return below that skips the
    actual build (nothing to build, no thread pool, already in flight
    with no new work) also finishes that slot's toast instead of leaving
    it stuck at "pyramid started" forever.
    """
    from shared.image_processing.pyramid_registry import ensure_pyramid
    from shared.image_processing.tiled_pixel_store import TiledPixelStore
    from shared.rendering.image_identity import image_uid

    if not isinstance(store, TiledPixelStore) or not store.is_open:
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return
    pyramid = ensure_pyramid(store)
    if pyramid is None or pyramid.is_complete():
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return
    uid = image_uid(store)
    if uid in controller._pyramid_builds:
        return
    thread_pool = getattr(controller.context, "thread_pool", None) if controller.context else None
    if thread_pool is None:
        if slot_id is not None:
            finish_loading_toast(controller, slot_id)
        return

    from shared.image_processing.pyramid_pixel_store import estimate_total_levels
    from sli_ui_toolkit.workers import GenericWorker

    controller._pyramid_builds.add(uid)
    if slot_id is not None:
        controller._pyramid_toast_slot[uid] = slot_id
        bump_loading_toast_pyramid_started(controller, slot_id)
    total_levels = estimate_total_levels(store.width, store.height)

    def should_abort() -> bool:
        return not pyramid.valid

    def build_task(progress_callback=None):
        while pyramid.build_next_level(should_abort=should_abort):
            complete = pyramid.is_complete()
            if progress_callback is not None:
                progress_callback((uid, pyramid.level_count, total_levels, complete))
        return None

    worker = GenericWorker(build_task)
    worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
    worker.signals.partial_result.connect(controller._on_pyramid_level_ready)
    worker.signals.finished.connect(
        lambda uid=uid: controller._pyramid_builds.discard(uid)
    )
    thread_pool.start(worker)


def on_pyramid_level_ready(controller, payload=None) -> None:
    canvas = getattr(controller.widget, "canvas", None)
    if canvas is not None:
        canvas.request_view_update()
    if not isinstance(payload, tuple) or len(payload) != 4:
        return
    uid, level_count, total_levels, complete = payload
    slot_id = controller._pyramid_toast_slot.get(uid)
    if slot_id is None:
        return
    if complete:
        controller._pyramid_toast_slot.pop(uid, None)
        finish_loading_toast(controller, slot_id)
    else:
        fraction = level_count / max(total_levels, 1)
        percent = PYRAMID_START_PROGRESS + int(
            fraction * (100 - PYRAMID_START_PROGRESS)
        )
        set_loading_toast_progress(controller, slot_id, percent)


def load_initial_image(controller, path: Path) -> tuple[Any, bool]:
    """Fast path for large sources: a bounded preview shown immediately
    while the full-res ``TiledPixelStore`` decodes in the background --
    mirrors image_compare's progressive load
    (``tabs.image_compare._session_controller._load_image_async``).

    Returns ``(image, is_preview)``; ``image`` is ``None`` on failure.
    """
    import time

    from shared.image_processing.progressive_loader import (
        load_preview_image,
        should_use_progressive_load,
    )

    t0 = time.perf_counter()
    try:
        if should_use_progressive_load(str(path)):
            preview = load_preview_image(str(path))
            if preview is not None:
                logger.debug(
                    "[preview-load] %s: preview ready in %.3fs (%dx%d)",
                    path,
                    time.perf_counter() - t0,
                    preview.width(),
                    preview.height(),
                )
                return preview, True
    except Exception:
        logger.debug(
            "Progressive preview failed for %s, falling back to full load",
            path,
            exc_info=True,
        )
    # start_pyramid=False: the slot this image will land in doesn't exist
    # yet at this point (callers create it from the returned image), so
    # there is no slot_id yet to drive the loading toast through the
    # pyramid stage. Callers start the pyramid themselves once the slot
    # (and its toast) exists -- see on_images_dropped/load_single_auto.
    image = read_image(controller, path, start_pyramid=False)
    logger.debug(
        "[preview-load] %s: no preview, full read in %.3fs",
        path,
        time.perf_counter() - t0,
    )
    return image, False


def load_full_resolution_async(controller, path: Path, slot_id: int) -> None:
    thread_pool = getattr(controller.context, "thread_pool", None) if controller.context else None
    if thread_pool is None:
        store = read_image(controller, path, start_pyramid=False)
        apply_full_resolution(controller, slot_id, path, store)
        return

    from sli_ui_toolkit.workers import GenericWorker

    def load_full_task(path_str: str):
        from shared.image_processing import pixel_cache_registry
        from shared.image_processing.tiled_pixel_store import TiledPixelStore

        cached = pixel_cache_registry.lookup(path_str)
        if cached is not None:
            cache_path, width, height = cached
            return TiledPixelStore.from_embedded_cache(cache_path, width, height)
        return TiledPixelStore.from_path(path_str)

    worker = GenericWorker(load_full_task, str(path))
    worker.signals.result.connect(
        lambda store, p=path, sid=slot_id: controller._apply_full_resolution(sid, p, store)
    )
    worker.signals.error.connect(
        lambda err, p=path, sid=slot_id: controller._on_full_resolution_error(p, sid, err)
    )
    thread_pool.start(worker)


def on_full_resolution_error(controller, path: Path, slot_id: int, err) -> None:
    logger.error("Failed to load full resolution for %s: %s", path, err)
    dismiss_loading_toast(controller, slot_id)


def apply_full_resolution(controller, slot_id: int, path: Path, store) -> None:
    if store is None:
        dismiss_loading_toast(controller, slot_id)
        return
    slot = next((s for s in controller.widget.state.slots if s.id == slot_id), None)
    if slot is None or slot.path != path:
        # Slot was removed/replaced while the full-res decode was in
        # flight -- the preview it belonged to is already gone from the
        # tree, so this store would just leak.
        from shared.image_processing.tiled_pixel_store import close_pixel_store

        close_pixel_store(store)
        finish_loading_toast(controller, slot_id)
        return
    mark_full_res_ready(controller, slot_id)
    from tabs.multi_compare.scene import actions as mc_actions

    controller.widget.store.dispatch(mc_actions.replace_slot_image(slot_id, store))
    start_pyramid_build(controller, store, slot_id=slot_id)


def load_single_auto(controller, path: Path) -> None:
    image, is_preview = load_initial_image(controller, path)
    if image is None:
        return
    sid = controller.widget.add_image_auto(path, image, label=path.stem)
    if sid is not None:
        show_loading_toast(controller, sid)
        if is_preview:
            load_full_resolution_async(controller, path, sid)
        else:
            mark_full_res_ready(controller, sid)
            start_pyramid_build(controller, image, slot_id=sid)


def on_images_dropped(controller, paths: list, target, side) -> None:
    """target: tuple (target_path_or_None, target_root_bool); side: 'left'/'right'/..."""
    from tabs.multi_compare.models import find_path

    target_path, target_root = (
        target if isinstance(target, tuple) else (None, False)
    )

    last_added: int | None = None
    for i, raw_path in enumerate(paths):
        path = Path(raw_path) if not isinstance(raw_path, Path) else raw_path
        image, is_preview = load_initial_image(controller, path)
        if image is None:
            continue
        if i == 0:
            sid = controller.widget.add_image_at(
                path, image, path.stem, target_path, side, target_root
            )
        else:
            next_side = "right" if side in ("left", "right") else "bottom"
            next_path: tuple[int, ...] | None = None
            if last_added is not None:
                found = find_path(controller.widget.state.root, last_added)
                next_path = tuple(found) if found is not None else None
            if next_path is None:
                sid = controller.widget.add_image_auto(path, image, path.stem)
            else:
                sid = controller.widget.add_image_at(
                    path, image, path.stem, next_path, next_side, False
                )
        if sid is not None:
            last_added = sid
            show_loading_toast(controller, sid)
            if is_preview:
                load_full_resolution_async(controller, path, sid)
            else:
                mark_full_res_ready(controller, sid)
                start_pyramid_build(controller, image, slot_id=sid)
