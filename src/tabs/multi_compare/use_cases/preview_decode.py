# Audit-Meta: pattern=thin-owner reason="A2 preview single-flight + bounded full-res stage fan-out via replace_slot_image"
"""Async first-image staging for the Multi Compare tab — preview decode in a
``GenericWorker`` with ``replace_slot_image`` slot fill on result.

Split out of ``use_cases/loading.py`` (file-size policy per
``docs/dev/CODE_PATTERNS.md``): ``loading.py`` keeps the sync decode
primitives, toast lifecycle, pyramid builds and the full-res second
stage; this module owns the P2 drop/add shape — imageless slot first, preview in
a worker (IC ``ImageLoadService.ensure_async`` parity), full-res second
stage. Every function here takes the controller as its first argument,
same calling convention as ``loading.py``.

A2 (decode single-flight + never-silent): preview-stage inflight map
keyed ``(normpath, mtime_ns, size)`` (IC ``ImageLoadService.key_for``
parity, minus crop/box — MC slots own their stores, no shared pixel
cache), ``AbortSignal``-style cancel on ``remove_slot``, forced
progressive preview (preview-miss kicks the bounded full stage instead
of stalling the preview worker), bounded full-res second stage
(``_FULL_MAX_CONCURRENT`` FIFO). Stale guards use the central
``_same_fs_path`` helper (delegates to ``loading._same_fs_path`` — one
impl): a missing slot dismisses silently, a recycled id (newer slot
reused the ``max+1`` id with a different path) is left untouched.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("ImproveImgSLI")

#: Bound for the full-res second stage (A2): at most this many full
#: decodes in flight; the rest wait in a FIFO queue. Preview workers stay
#: unbounded (fast, ~1024px) — only the heavy full decode is throttled so
#: one multi-add cannot storm the pool while previews still land fast.
_FULL_MAX_CONCURRENT = 2


class _AbortSignal:
    """Cancellation token, ``AbortSignal``-style (IC ``pipeline/abort`` parity).

    Local to multi_compare (no cross-tab import — tab isolation): one
    signal per single-flight key; every async stage checks
    ``is_aborted()`` before/after decode, ``cancel_slot_loads`` aborts
    entries with no live waiters left.
    """

    def __init__(self) -> None:
        self._aborted = False

    def abort(self) -> None:
        self._aborted = True

    def is_aborted(self) -> bool:
        return self._aborted

    def __call__(self) -> bool:
        return self._aborted

    def __bool__(self) -> bool:
        return not self._aborted


def new_abort_signal() -> _AbortSignal:
    """Factory for full-stage signals owned by ``loading.py`` (same token type)."""
    return _AbortSignal()


def _same_fs_path(a: Path | str, b: Path | str) -> bool:
    """Central normalized path-equality guard (single impl lives in ``loading``)."""
    from tabs.multi_compare.use_cases import loading as _loading

    return _loading._same_fs_path(a, b)


def _fs_key(path: Path | str) -> tuple:
    """Single-flight key ``(normpath, mtime_ns, size)`` (IC ``key_for`` parity).

    ``mtime+size`` keeps an overwritten-in-place file from colliding with
    its own stale decode; ``normpath`` heals textual variants of the same
    file (``/x/./f.png`` vs ``/x/f.png``, ``str`` vs ``Path``).
    """
    try:
        norm = os.path.normpath(os.fspath(path))
    except Exception:
        return (str(path), 0, 0)
    try:
        st = os.stat(norm)
        return (
            norm,
            int(getattr(st, "st_mtime_ns", 0) or 0),
            int(getattr(st, "st_size", 0) or 0),
        )
    except OSError:
        return (norm, 0, 0)


def _preview_inflight(controller) -> dict:
    """Preview-stage inflight map: key → ``{"signal", "waiters": [(slot_id, path)]}``."""
    entries = getattr(controller, "_mc_preview_inflight", None)
    if entries is None:
        entries = {}
        try:
            controller._mc_preview_inflight = entries
        except Exception:
            return {}
    return entries if isinstance(entries, dict) else {}


def _full_active(controller) -> dict:
    """Full-stage active map: slot_id → ``{"signal", "path"}`` (bounded)."""
    active = getattr(controller, "_mc_full_active", None)
    if active is None:
        active = {}
        try:
            controller._mc_full_active = active
        except Exception:
            return {}
    return active if isinstance(active, dict) else {}


def _full_queue(controller) -> list:
    """Full-stage FIFO queue: ``[(slot_id, path)]`` waiting for a bound slot."""
    queue = getattr(controller, "_mc_full_queue", None)
    if queue is None:
        queue = []
        try:
            controller._mc_full_queue = queue
        except Exception:
            return []
    return queue if isinstance(queue, list) else []


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
    """Decode the display-tier preview off the GUI thread (P2, single-flight A2).

    Mirrors image_compare's ``ImageLoadService.ensure_async`` first stage:
    the drop handler (already deferred past ``finish()`` via
    ``singleShot(0)``) only creates the imageless slot + toast
    synchronously; the bounded ``load_preview_image`` decode runs in a
    ``GenericWorker`` and fills the slot via ``replace_slot_image`` on
    result (``PutPreviewAction``-style), with the full-res decode as the
    second stage.

    Single-flight: a second ``load_preview_async`` for the same
    ``(normpath, mtime, size)`` key while the first is still in flight
    attaches to its waiters instead of starting a second decode
    (double-click Add = 1 preview decode, fanned out to both slots).
    The worker decodes the preview ONLY — a preview-miss no longer
    stalls inside a full decode in the preview worker; it kicks the
    bounded full stage per waiter instead.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    key = _fs_key(path)
    entries = _preview_inflight(controller)
    ent = entries.get(key)
    if ent is not None:
        try:
            aborted = ent["signal"].is_aborted()
        except Exception:
            aborted = True
        if not aborted:
            ent["waiters"].append((slot_id, path))
            logger.debug(
                "[mc-preview-singleflight] dedup %s key=%s waiters=%d",
                path,
                key,
                len(ent["waiters"]),
            )
            return
        entries.pop(key, None)
    sig = _AbortSignal()
    entries[key] = {"signal": sig, "waiters": [(slot_id, path)]}

    thread_pool = getattr(controller.context, "thread_pool", None) if getattr(controller, "context", None) else None
    if thread_pool is None:
        # Headless/tests without a pool: preserve the old synchronous shape
        # (inline decode cannot dedup — waiters is always length 1 here).
        entries.pop(key, None)
        try:
            image, is_preview = load_initial_image(controller, path)
        except Exception as err:
            on_preview_error(controller, path, slot_id, err)
            return
        on_preview_ready(controller, slot_id, path, (image, is_preview))
        return

    from sli_ui_toolkit.workers import GenericWorker

    crop_service = _loading._get_crop_service(controller)

    def preview_task(path_str: str, svc, sig_ref=sig):
        # NOTE: GenericWorker emits ``result`` only for non-None returns,
        # so this task ALWAYS returns a ``(preview_or_None, True)`` tuple —
        # a bare ``None`` (miss/abort) would be swallowed and the waiters
        # would never fan out.
        from shared.image_processing.progressive_loader import (
            load_preview_image,
            should_use_progressive_load,
        )

        # Forced progressive (IC parity): always preview first, even for
        # small files — never skip straight to the full decode here.
        _ = should_use_progressive_load
        try:
            if sig_ref.is_aborted():
                return (None, True)
        except Exception:
            pass
        try:
            preview = load_preview_image(path_str, crop_service=svc)
        except Exception:
            logger.debug(
                "Progressive preview failed for %s, falling back to full load",
                path_str,
                exc_info=True,
            )
            return (None, True)
        try:
            if sig_ref.is_aborted():
                return (None, True)
        except Exception:
            pass
        if preview is not None and not preview.isNull():
            return (preview, True)
        return (None, True)

    worker = GenericWorker(preview_task, str(path), crop_service)
    worker.signals.result.connect(
        lambda res: _deliver_preview_worker_result(controller, key, res[0])
    )
    worker.signals.error.connect(
        lambda err: _deliver_preview_worker_error(controller, key, err)
    )

    def _cleanup():
        try:
            cur = entries.get(key)
            if cur is not None and cur.get("signal") is sig:
                entries.pop(key, None)
        except Exception:
            pass

    try:
        worker.signals.finished.connect(_cleanup)
    except Exception:
        pass
    try:
        thread_pool.start(worker)
    except Exception:
        logger.exception("Failed to start preview worker for %s", path)
        entries.pop(key, None)
        _deliver_preview_worker_error(controller, key, RuntimeError("preview worker failed to start"))


def _deliver_preview_worker_result(controller, key, preview) -> None:
    """Fan a finished preview worker out to its waiter slots."""
    from tabs.multi_compare.use_cases import loading as _loading

    ent = _preview_inflight(controller).pop(key, None)
    if ent is None:
        return
    try:
        aborted = ent["signal"].is_aborted()
    except Exception:
        aborted = False
    waiters = list(ent.get("waiters", ()))
    if aborted:
        # Orphan delivery (all waiters cancelled): silent dismiss, no
        # toast-done, no bus event — remove-mid-load stays clean.
        for sid, _p in waiters:
            try:
                _loading.dismiss_loading_toast(controller, sid)
            except Exception:
                pass
        return
    if preview is None:
        # Preview-miss: the preview tier stays imageless; each waiter goes
        # through the bounded full stage (own decode — this worker already
        # returned, nothing is blocked here).
        for sid, p in waiters:
            try:
                _loading.load_full_resolution_async(controller, p, sid)
            except Exception:
                logger.exception("Failed to kick full-res stage for %s", p)
        return
    for sid, p in waiters:
        try:
            on_preview_ready(controller, sid, p, (preview, True))
        except Exception:
            logger.exception("Failed to deliver preview to slot %s", sid)


def _deliver_preview_worker_error(controller, key, err) -> None:
    """Fan a failed preview worker out to its waiter slots."""
    from tabs.multi_compare.use_cases import loading as _loading

    ent = _preview_inflight(controller).pop(key, None)
    if ent is None:
        return
    try:
        aborted = ent["signal"].is_aborted()
    except Exception:
        aborted = False
    waiters = list(ent.get("waiters", ()))
    if aborted:
        for sid, _p in waiters:
            try:
                _loading.dismiss_loading_toast(controller, sid)
            except Exception:
                pass
        return
    for sid, p in waiters:
        try:
            on_preview_error(controller, p, sid, err)
        except Exception:
            logger.exception("Failed to deliver preview error to slot %s", sid)


def cancel_slot_loads(controller, slot_id: int) -> None:
    """Detach ``slot_id`` from preview waiters + full queue/active (A2 cancel-on-remove).

    Entries left with no live waiters are aborted ``AbortSignal``-style so
    their late results deliver silently (no toast-done, no bus event, no
    touch of a recycled id). The slot's own toast is dismissed here — the
    stale-delivery paths must NOT dismiss again (a recycled id's toast
    belongs to the newer generation).
    """
    from tabs.multi_compare.use_cases import loading as _loading

    try:
        entries = _preview_inflight(controller)
        for key in list(entries.keys()):
            ent = entries.get(key)
            if not ent:
                continue
            waiters = list(ent.get("waiters", ()))
            kept = [(s, p) for (s, p) in waiters if s != slot_id]
            if len(kept) == len(waiters):
                continue
            ent["waiters"] = kept
            if not kept:
                try:
                    ent["signal"].abort()
                except Exception:
                    pass
                entries.pop(key, None)
    except Exception:
        logger.exception("Failed to cancel preview inflight for slot %s", slot_id)
    try:
        cancel_full_for_slot(controller, slot_id)
    except Exception:
        logger.exception("Failed to cancel full-res stage for slot %s", slot_id)
    try:
        _loading.dismiss_loading_toast(controller, slot_id)
    except Exception:
        pass


def remove_slot_with_cancel(controller, slot_id: int) -> None:
    """Controller-level slot removal: abort inflight decodes first, then dispatch."""
    try:
        cancel_slot_loads(controller, slot_id)
    except Exception:
        logger.exception("Failed to cancel inflight loads for slot %s", slot_id)
    from tabs.multi_compare.scene import actions as mc_actions

    try:
        controller.widget.store.dispatch(mc_actions.remove_slot(slot_id))
    except Exception:
        logger.exception("Failed to remove slot %s", slot_id)


def queue_full_resolution(controller, path: Path, slot_id: int) -> None:
    """Bounded full-res second stage (A2): per-slot workers, FIFO overflow.

    Stores are NEVER shared between slots (the reducer keeps removed
    slots' stores alive for undo — sharing would alias undo snapshots and
    ``close_pixel_store`` on a stale delivery would break the live slot).
    At most ``_FULL_MAX_CONCURRENT`` decodes run at once; the rest wait in
    ``_mc_full_queue`` and start as workers finish.
    """
    try:
        queue = _full_queue(controller)
        queue[:] = [(s, p) for (s, p) in queue if s != slot_id]
        queue.append((slot_id, path))
    except Exception:
        logger.exception("Failed to queue full-res load for %s", path)
        return
    _pump_full_stage(controller)


def _pump_full_stage(controller) -> None:
    """Start queued full-res workers while under the concurrency bound."""
    from tabs.multi_compare.use_cases import loading as _loading

    try:
        active = _full_active(controller)
        queue = _full_queue(controller)
    except Exception:
        return
    thread_pool = getattr(controller.context, "thread_pool", None) if getattr(controller, "context", None) else None
    if thread_pool is None:
        # Headless/tests without a pool: drain inline (legacy sync shape).
        while queue:
            sid, p = queue.pop(0)
            try:
                store = _loading.read_image(controller, p, start_pyramid=False)
            except Exception as err:
                _on_full_worker_error(controller, sid, p, err, None)
                continue
            _on_full_worker_result(controller, sid, p, store, None)
        return

    from sli_ui_toolkit.workers import GenericWorker

    while queue and len(active) < _FULL_MAX_CONCURRENT:
        sid, p = queue.pop(0)
        if sid in active:
            cur = active.get(sid) or {}
            try:
                same = _loading._same_fs_path(cur.get("path", p), p)
            except Exception:
                same = True
            if same:
                continue  # identical decode already in flight
            try:
                if cur.get("signal") is not None:
                    cur["signal"].abort()
            except Exception:
                pass
            active.pop(sid, None)
        try:
            slots = list(controller.widget.state.slots)
        except Exception:
            slots = None
        if slots is not None:
            slot = next((s for s in slots if s.id == sid), None)
            if slot is None:
                # Orphan queued (slot removed while queued): silent
                # dismiss, no toast-done, no bus event.
                try:
                    _loading.dismiss_loading_toast(controller, sid)
                except Exception:
                    pass
                continue
            try:
                same = _loading._same_fs_path(slot.path, p)
            except Exception:
                same = True
            if not same:
                # Id recycled: the newer generation queued its own entry;
                # leave its toast alone.
                continue
        crop_service = _loading._get_crop_service(controller)
        sig = _AbortSignal()
        active[sid] = {"signal": sig, "path": p}

        def load_full_task(path_str: str, svc, sig_ref=sig):
            try:
                if sig_ref.is_aborted():
                    return None
            except Exception:
                pass
            from shared.image_processing.pixel_cache_loader import load_pixel_store
            from shared.image_processing import embedded_pixel_cache as _emb_mc2

            store = load_pixel_store(path_str, crop_service=svc, embedded_cache=_emb_mc2)
            try:
                if sig_ref.is_aborted():
                    from shared.image_processing.tiled_pixel_store import close_pixel_store

                    try:
                        close_pixel_store(store)
                    except Exception:
                        pass
                    return None
            except Exception:
                pass
            return store

        worker = GenericWorker(load_full_task, str(p), crop_service)
        worker.signals.result.connect(
            lambda store, sid=sid, p=p, sig_ref=sig: _on_full_worker_result(
                controller, sid, p, store, sig_ref
            )
        )
        worker.signals.error.connect(
            lambda err, sid=sid, p=p, sig_ref=sig: _on_full_worker_error(
                controller, sid, p, err, sig_ref
            )
        )

        def _finished(sid=sid, sig_ref=sig):
            try:
                cur = _full_active(controller).get(sid)
                if cur is not None and cur.get("signal") is sig_ref:
                    _full_active(controller).pop(sid, None)
            except Exception:
                pass
            _pump_full_stage(controller)

        try:
            worker.signals.finished.connect(_finished)
        except Exception:
            pass
        try:
            thread_pool.start(worker)
        except Exception:
            logger.exception("Failed to start full-res worker for %s", p)
            try:
                active.pop(sid, None)
            except Exception:
                pass
            _on_full_worker_error(
                controller, sid, p, RuntimeError("full-res worker failed to start"), sig
            )


def _on_full_worker_result(controller, slot_id: int, path: Path, store, sig_ref) -> None:
    """Deliver a finished full-res worker: superseded/cancelled drops silently."""
    try:
        cur = _full_active(controller).get(slot_id)
        if sig_ref is not None and (cur is None or cur.get("signal") is not sig_ref):
            if store is not None:
                try:
                    from shared.image_processing.tiled_pixel_store import close_pixel_store

                    close_pixel_store(store)
                except Exception:
                    pass
            _pump_full_stage(controller)
            return
        _full_active(controller).pop(slot_id, None)
    except Exception:
        pass
    try:
        controller._apply_full_resolution(slot_id, path, store)
    except Exception:
        logger.exception("Failed to apply full resolution to slot %s", slot_id)
    _pump_full_stage(controller)


def _on_full_worker_error(controller, slot_id: int, path: Path, err, sig_ref) -> None:
    """Deliver a failed full-res worker (orphan/recycled stays silent via guards)."""
    try:
        cur = _full_active(controller).get(slot_id)
        if sig_ref is not None and (cur is None or cur.get("signal") is not sig_ref):
            _pump_full_stage(controller)
            return
        _full_active(controller).pop(slot_id, None)
    except Exception:
        pass
    try:
        controller._on_full_resolution_error(path, slot_id, err)
    except Exception:
        logger.exception("Failed to deliver full-res error to slot %s", slot_id)
    _pump_full_stage(controller)


def cancel_full_for_slot(controller, slot_id: int) -> None:
    """Drop queued + abort active full-res work for ``slot_id`` (silent orphan)."""
    try:
        _full_queue(controller)[:] = [
            (s, p) for (s, p) in _full_queue(controller) if s != slot_id
        ]
    except Exception:
        pass
    try:
        cur = _full_active(controller).pop(slot_id, None)
        if cur is not None and cur.get("signal") is not None:
            try:
                cur["signal"].abort()
            except Exception:
                pass
    except Exception:
        pass


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
    the ``TiledPixelStore`` close in ``apply_full_resolution``. A recycled
    id (newer slot, different path) is left untouched — its toast belongs
    to the live generation.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    try:
        slots = list(controller.widget.state.slots)
    except Exception:
        slots = []
    slot = next((s for s in slots if s.id == slot_id), None)
    if slot is None:
        _loading.dismiss_loading_toast(controller, slot_id)
        return
    try:
        same = _same_fs_path(slot.path, path)
    except Exception:
        same = False
    if not same:
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
    must never remove a newer slot that reused the id — and an orphan
    (slot already gone) stays silent: no toast-done, no error-toast, the
    user cancelled it.
    """
    from tabs.multi_compare.use_cases import loading as _loading

    try:
        slots = list(controller.widget.state.slots)
    except Exception:
        slots = []
    slot = next((s for s in slots if s.id == slot_id), None)
    if slot is None:
        try:
            _loading.dismiss_loading_toast(controller, slot_id)
        except Exception:
            pass
        return
    try:
        same = _same_fs_path(slot.path, path)
    except Exception:
        same = False
    if not same:
        return
    logger.error("Failed to load preview for %s: %s", path, err, exc_info=True)
    try:
        from tabs.multi_compare.scene import actions as mc_actions

        controller.widget.store.dispatch(mc_actions.remove_slot(slot_id))
    except Exception:
        logger.exception("Failed to remove failed-load slot %s", slot_id)
    _loading.dismiss_loading_toast(controller, slot_id)
    _loading._emit_mc_load_error(controller, path, err)
