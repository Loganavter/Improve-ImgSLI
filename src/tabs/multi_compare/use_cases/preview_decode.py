"""Async first-image staging for the Multi Compare tab — preview decode in a
``GenericWorker`` with ``replace_slot_image`` slot fill on result.

Split out of ``use_cases/loading.py`` (file-size policy per
``docs/dev/CODE_PATTERNS.md``): ``loading.py`` keeps the sync decode
primitives, toast lifecycle, pyramid builds and the full-res second stage;
this module owns the P2 drop/add shape — imageless slot first, preview in
a worker (IC ``ImageLoadService.ensure_async`` parity), full-res second
stage. Every function here takes the controller as its first argument,
same calling convention as ``loading.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ImproveImgSLI")


def load_initial_image(controller, path: Path) -> tuple[Any, bool]:
    """Synchronous preview-or-full decode — no-pool fallback only.

    Bounded preview first, full-res fallback on preview-miss — mirrors
    image_compare's progressive load
    (``tabs.image_compare._session_controller._load_image_async``).

    Since P2 the drop/add paths pre-create an imageless slot and decode in
    a ``GenericWorker`` (``load_preview_async`` below); this function stays
    as the synchronous fallback for contexts without a thread pool
    (headless/tests) and must NOT be called on the GUI thread for real
    drops — a preview-miss here is a full ``read_image`` stall.

    ``start_pyramid=False``: the toast/pyramid staging is driven by the
    slot-fill path (``apply_preview`` / ``apply_full_resolution`` in
    ``loading.py``), not here.

    Returns ``(image, is_preview)``; ``image`` is ``None`` on failure.
    """
    import time

    from shared.image_processing.progressive_loader import (
        load_preview_image,
        should_use_progressive_load,
    )
    from tabs.multi_compare.use_cases import loading as _loading

    t0 = time.perf_counter()
    crop_service = _loading._get_crop_service(controller)
    try:
        if should_use_progressive_load(str(path)):
            preview = load_preview_image(str(path), crop_service=crop_service)
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
    image = _loading.read_image(controller, path, start_pyramid=False)
    logger.debug(
        "[preview-load] %s: no preview, full read in %.3fs",
        path,
        time.perf_counter() - t0,
    )
    return image, False


def load_preview_async(controller, path: Path, slot_id: int) -> None:
    """Decode the display-tier preview off the GUI thread (P2).

    Mirrors image_compare's ``ImageLoadService.ensure_async`` first stage:
    the drop handler (already deferred past ``finish()`` via
    ``singleShot(0)``) only creates the imageless slot + toast
    synchronously; the bounded ``load_preview_image`` decode runs in a
    ``GenericWorker`` and fills the slot via ``replace_slot_image`` on
    result (``PutPreviewAction``-style), with the full-res decode as the
    second stage. Preview-miss (no preview for the file) decodes full-res
    in the same worker so there is no extra thread hop — the same
    single-worker shape as IC's ``_worker_body``.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    thread_pool = getattr(controller.context, "thread_pool", None) if getattr(controller, "context", None) else None
    if thread_pool is None:
        # Headless/tests without a pool: preserve the old synchronous shape.
        image, is_preview = load_initial_image(controller, path)
        on_preview_ready(controller, slot_id, path, (image, is_preview))
        return

    from sli_ui_toolkit.workers import GenericWorker

    crop_service = _loading._get_crop_service(controller)

    def preview_task(path_str: str, svc):
        from shared.image_processing.progressive_loader import (
            load_preview_image,
            should_use_progressive_load,
        )

        try:
            if should_use_progressive_load(path_str):
                preview = load_preview_image(path_str, crop_service=svc)
                if preview is not None and not preview.isNull():
                    return (preview, True)
        except Exception:
            logger.debug(
                "Progressive preview failed for %s, falling back to full load",
                path_str,
                exc_info=True,
            )
        # Preview-miss: full decode in the same worker (IC parity).
        from shared.image_processing import embedded_pixel_cache as _emb_mc
        from shared.image_processing.pixel_cache_loader import load_pixel_store

        store = load_pixel_store(path_str, crop_service=svc, embedded_cache=_emb_mc)
        return (store, False)

    worker = GenericWorker(preview_task, str(path), crop_service)
    worker.signals.result.connect(
        lambda res, p=path, sid=slot_id: controller._on_preview_ready(sid, p, res)
    )
    worker.signals.error.connect(
        lambda err, p=path, sid=slot_id: controller._on_preview_error(p, sid, err)
    )
    thread_pool.start(worker)


def on_preview_ready(controller, slot_id: int, path: Path, result) -> None:
    """Fill a pre-created imageless slot with the worker-decoded tier.

    ``result`` is the ``(image, is_preview)`` tuple from
    ``load_preview_async``'s worker: a ``QImage`` preview takes the
    ``replace_slot_image`` preview tier and kicks the full-res second
    stage; a ``TiledPixelStore`` (preview-miss decoded in the same worker)
    goes through the regular full-res apply path.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    image, is_preview = result
    if image is None:
        on_preview_error(controller, path, slot_id, RuntimeError("preview decode returned no image"))
        return
    if is_preview:
        apply_preview(controller, slot_id, path, image)
        return
    _loading.apply_full_resolution(controller, slot_id, path, image)


def apply_preview(controller, slot_id: int, path: Path, preview) -> None:
    """``PutPreviewAction``-style slot fill: imageless slot → preview tier.

    Dispatches ``replace_slot_image`` (pure reducer, dispatch-only mutation
    per STORE invariants) and kicks the full-res second stage. Tiers stay
    visible throughout: a stale slot (removed/replaced mid-decode) only
    drops its toast — the ``QImage`` needs no lifecycle handling, unlike
    the ``TiledPixelStore`` close in ``apply_full_resolution``.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    slot = next((s for s in controller.widget.state.slots if s.id == slot_id), None)
    if slot is None or not _loading._same_fs_path(slot.path, path):
        _loading.dismiss_loading_toast(controller, slot_id)
        return
    from tabs.multi_compare.scene import actions as mc_actions

    controller.widget.store.dispatch(mc_actions.replace_slot_image(slot_id, preview))
    _loading.load_full_resolution_async(controller, path, slot_id)


def on_preview_error(controller, path: Path, slot_id: int, err) -> None:
    """A preview worker failed: drop the pre-created imageless slot.

    Sync-UX parity: the old synchronous path skipped slot creation on
    failure, so the failed file must not leave an imageless leaf behind
    either (imageless leaves are skipped by the composition builder and
    would read as a blank hole). The ``slot.path`` guard is load-bearing:
    slot ids can be recycled after removal (``max+1``), so a late worker
    must never remove a newer slot that reused the id.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    logger.error("Failed to load preview for %s: %s", path, err, exc_info=True)
    try:
        slot = next((s for s in controller.widget.state.slots if s.id == slot_id), None)
        if slot is not None and _loading._same_fs_path(slot.path, path):
            from tabs.multi_compare.scene import actions as mc_actions

            controller.widget.store.dispatch(mc_actions.remove_slot(slot_id))
    except Exception:
        logger.exception("Failed to remove failed-load slot %s", slot_id)
    _loading.dismiss_loading_toast(controller, slot_id)
    _loading._emit_mc_load_error(controller, path, err)
