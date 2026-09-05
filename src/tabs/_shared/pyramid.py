"""Shared pyramid-build coordinator for IC and MC (B3 dedup).

Parameterizes the abort predicate that previously differed meaningfully:

* IC: ``lambda: task_id != controller._unification_task_id`` (staleness)
* MC: ``lambda: not pyramid.valid`` (store closed / generation)

Single progress math, single toast-slot dict, single worker lifecycle.
State-owning collaborator (CODE_PATTERNS.md "who owns the state").

Usage::

    toast = LoadingToastCoordinator(...)
    pyramid = PyramidBuildCoordinator(
        get_thread_pool=lambda: controller.thread_pool,
        toast_coordinator=toast,
        get_pyramid=lambda store: pyramid_registry.ensure_pyramid(store),
        estimate_levels=lambda w, h: estimate_total_levels(w, h),
        request_view_update=lambda: controller._schedule_image_canvas_update(),
        invalidate_render=lambda complete: controller._invalidate_image_canvas_render_state() if complete else None,
    )
    # start:
    pyramid.start_build(store, slot_id=slot, should_abort=lambda: task_id != ctrl._unification_task_id)
    # signal from worker:
    pyramid.on_level_ready(payload)

Both tabs keep thin delegators so controller API is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from sli_ui_toolkit.workers import GenericWorker

from tabs._shared.loading_toast import PYRAMID_START_PROGRESS, toast_debug

logger = logging.getLogger("ImproveImgSLI")


def _pyramid_build_loop(
    pyramid,
    should_abort: Callable[[], bool] | None,
    uid: int,
    total_levels: int,
    progress_callback=None,
):
    """Worker body: build levels until complete or aborted, emitting progress.

    Phase 5: await idle between levels (let event loop breathe) — the worker
    thread yields briefly so the UI thread can paint/use LOD 0 while higher
    levels build. Previously a tight loop starved the thread_pool.
    """
    import time

    ran_levels = 0
    last_complete = False
    while pyramid.build_next_level(should_abort=should_abort):
        ran_levels += 1
        last_complete = pyramid.is_complete()
        if progress_callback is not None:
            progress_callback((uid, pyramid.level_count, total_levels, last_complete))
        # idle between levels: yield to UI / other workers
        if not last_complete:
            try:
                time.sleep(0.002)
            except Exception:
                pass
            if should_abort is not None and should_abort():
                break
    if ran_levels:
        exit_reason = "complete" if last_complete else "abort"
    else:
        try:
            if pyramid.is_complete():
                exit_reason = "complete-unreported"
            elif should_abort is not None and should_abort():
                exit_reason = "abort-before-first-level"
            else:
                exit_reason = "stalled-no-level"
        except Exception:
            exit_reason = "stalled-no-level"
    toast_debug(
        "pyramid loop exit: uid=%s levels=%s/%s reason=%s",
        uid,
        ran_levels,
        total_levels,
        exit_reason,
    )
    return None


class PyramidBuildCoordinator:
    """Owns pyramid worker lifecycle + toast slot routing (B3).

    Args:
        get_thread_pool: ``() -> QThreadPool | None`` (IC: controller.thread_pool,
            MC: controller.context.thread_pool).
        toast_coordinator: optional :class:`LoadingToastCoordinator`; if given,
            progress / completion drives the toast.
        get_pyramid: ``(store) -> PyramidPixelStore | None``; defaults to
            ``pyramid_registry.ensure_pyramid``.
        estimate_levels: ``(w, h) -> int``; defaults to
            ``pyramid_pixel_store.estimate_total_levels``.
        request_view_update: called on every level (repaint / LOD refresh).
        invalidate_render: called with ``complete`` bool when a level completes
            that requires render-state invalidation (IC: pick_display_image flip).
    """

    def __init__(
        self,
        *,
        get_thread_pool: Callable[[], Any | None],
        toast_coordinator: Any | None = None,
        get_pyramid: Callable[[Any], Any | None] | None = None,
        estimate_levels: Callable[[int, int], int] | None = None,
        request_view_update: Callable[[], None] | None = None,
        invalidate_render: Callable[[bool], None] | None = None,
        get_store: Callable[[], Any | None] | None = None,
    ) -> None:
        self._get_thread_pool = get_thread_pool
        self._toast = toast_coordinator
        self._get_pyramid = get_pyramid
        self._estimate_levels = estimate_levels
        self._request_view_update = request_view_update
        self._invalidate_render = invalidate_render
        self._get_store = get_store

        self._pyramid_builds: set[int] = set()
        # uid -> slot_id / image_number
        self._pyramid_toast_slot: dict[int, int] = {}

    # --- compat properties (tests peek at controller sets) ---
    @property
    def pyramid_builds(self) -> set[int]:
        return self._pyramid_builds

    @property
    def pyramid_toast_slot(self) -> dict[int, int]:
        return self._pyramid_toast_slot

    # Back-compat alias used by IC ( _loading_toast_uid_slot )
    @property
    def loading_toast_uid_slot(self) -> dict[int, int]:
        return self._pyramid_toast_slot

    # --- core ---

    def _resolve_get_pyramid(self):
        if self._get_pyramid is not None:
            return self._get_pyramid
        try:
            from shared.image_processing.pyramid_registry import ensure_pyramid

            return ensure_pyramid
        except Exception:
            return lambda _s: None

    def _resolve_estimate(self):
        if self._estimate_levels is not None:
            return self._estimate_levels
        try:
            from shared.image_processing.pyramid_pixel_store import estimate_total_levels

            return estimate_total_levels
        except Exception:
            return lambda w, h: 1

    def start_build(
        self,
        store,
        *,
        slot_id: int | None = None,
        should_abort: Callable[[], bool] | None = None,
        on_level_ready: Callable[[Any], None] | None = None,
    ) -> bool:
        """Start a pyramid build for *store*; returns True iff a worker was started.

        Skipped cases (no pyramid, already complete, already in flight,
        no thread pool) finish the toast for *slot_id* via the toast coordinator
        instead of leaving it stuck at "pyramid started".
        """
        from shared.rendering.image_identity import image_uid

        get_pyramid = self._resolve_get_pyramid()

        # early toast finish helper
        def _finish_toast_if_needed():
            if slot_id is not None and self._toast is not None:
                try:
                    self._toast.finish(slot_id)
                except Exception:
                    pass

        pyramid = get_pyramid(store)
        if pyramid is None:
            toast_debug("pyramid skip: slot=%s reason=no-pyramid", slot_id)
            logger.debug(
                "[Pyramid] skip build: no pyramid for store %sx%s",
                getattr(store, "width", -1),
                getattr(store, "height", -1),
            )
            _finish_toast_if_needed()
            return False
        if pyramid.is_complete():
            toast_debug("pyramid skip: slot=%s reason=already-complete", slot_id)
            logger.debug(
                "[Pyramid] skip build: already complete for store %sx%s (levels=%d)",
                getattr(store, "width", -1),
                getattr(store, "height", -1),
                getattr(pyramid, "level_count", -1),
            )
            _finish_toast_if_needed()
            return False

        uid = image_uid(store)
        if uid in self._pyramid_builds:
            toast_debug(
                "pyramid skip: slot=%s reason=already-in-flight uid=%s (toast NOT remapped)",
                slot_id,
                uid,
            )
            logger.debug("[Pyramid] skip build: already in flight (uid=%s)", uid)
            _finish_toast_if_needed()
            return False

        thread_pool = self._get_thread_pool()
        if thread_pool is None:
            toast_debug("pyramid skip: slot=%s reason=no-thread-pool", slot_id)
            _finish_toast_if_needed()
            return False

        estimate = self._resolve_estimate()
        try:
            total_levels = estimate(store.width, store.height)
        except Exception:
            total_levels = 1

        self._pyramid_builds.add(uid)
        if slot_id is not None and self._toast is not None:
            self._pyramid_toast_slot[uid] = slot_id
            try:
                self._toast.bump_pyramid_started(slot_id)
            except Exception:
                pass
        elif slot_id is not None:
            self._pyramid_toast_slot[uid] = slot_id

        logger.info(
            "[Pyramid] build started for store %sx%s (uid=%s)",
            getattr(store, "width", -1),
            getattr(store, "height", -1),
            uid,
        )

        # capture should_abort; default is never abort
        abort = should_abort if should_abort is not None else lambda: False

        worker = GenericWorker(
            _pyramid_build_loop, pyramid, abort, uid, total_levels
        )
        worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
        # level progress
        target = on_level_ready if on_level_ready is not None else self.on_level_ready
        worker.signals.partial_result.connect(target)
        worker.signals.finished.connect(lambda uid=uid: self._on_build_finished(uid))
        thread_pool.start(worker)
        return True

    def _on_build_finished(self, uid: int) -> None:
        """Worker done: drop the in-flight mark; report a stuck toast mapping.

        Temporary [toast-debug] diagnostic: if the uid→slot mapping is still
        present here, no complete payload ever arrived (abort / stalled loop)
        and the slot's toast will hang forever.
        """
        self._pyramid_builds.discard(uid)
        slot_id = self._pyramid_toast_slot.pop(uid, None)
        toast_debug(
            "pyramid finished: uid=%s slot=%s mapping_stuck=%s",
            uid,
            slot_id,
            slot_id is not None,
        )
        if slot_id is not None and self._toast is not None:
            try:
                dismiss = getattr(self._toast, "dismiss", None)
                if callable(dismiss):
                    dismiss(slot_id)
                else:
                    self._toast.finish(slot_id)
            except Exception:
                pass

    def on_level_ready(self, payload) -> None:
        # Phase 5: publish lod_available per level instead of invalidate_render
        # per level. The canvas LOD selector consumes new levels without a
        # full pick-signature invalidation; only the final flip needs it.
        # We still call request_view_update for repaint, but publish lod_available
        # so subscribers can coalesce.
        store = None
        if self._get_store is not None:
            try:
                store = self._get_store()
            except Exception:
                store = None

        # publish lod_available for every level (including complete)
        if store is not None and hasattr(store, "publish"):
            try:
                store.publish("lod_available")
            except Exception:
                pass
        elif store is not None and hasattr(store, "emit_state_change"):
            try:
                store.emit_state_change("lod_available")
            except Exception:
                pass

        # UI refresh hooks (tab-specific) — view update on every level
        if self._request_view_update is not None:
            try:
                self._request_view_update()
            except Exception:
                pass

        if not isinstance(payload, tuple) or len(payload) != 4:
            toast_debug("level_ready: bad payload=%r", payload)
            return
        uid, level_count, total_levels, complete = payload

        # IC-style invalidate only on complete (final flip)
        if complete and self._invalidate_render is not None:
            try:
                self._invalidate_render(True)
            except Exception:
                pass

        slot_id = self._pyramid_toast_slot.get(uid)
        if slot_id is None:
            toast_debug(
                "level_ready: uid=%s level=%s/%s complete=%s NO slot mapping",
                uid,
                level_count,
                total_levels,
                complete,
            )
            return
        toast_debug(
            "level_ready: uid=%s slot=%s level=%s/%s complete=%s",
            uid,
            slot_id,
            level_count,
            total_levels,
            complete,
        )
        if self._toast is None:
            if complete:
                self._pyramid_toast_slot.pop(uid, None)
            return
        if complete:
            self._pyramid_toast_slot.pop(uid, None)
            try:
                self._toast.finish(slot_id)
            except Exception:
                pass
        else:
            fraction = level_count / max(total_levels, 1)
            percent = PYRAMID_START_PROGRESS + int(fraction * (100 - PYRAMID_START_PROGRESS))
            try:
                self._toast.set_progress(slot_id, percent)
            except Exception:
                pass
