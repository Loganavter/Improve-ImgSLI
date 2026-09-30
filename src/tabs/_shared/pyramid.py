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
    # lazy demand (QL-style zoom/dwell): build only until level k lands:
    pyramid.demand_level(store, k, should_abort=walk_abort_fn, on_ready=refresh_view)

Both tabs keep thin delegators so controller API is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from sli_ui_toolkit.workers import GenericWorker

from tabs._shared.loading_toast import PYRAMID_START_PROGRESS

logger = logging.getLogger("ImproveImgSLI")


def _pyramid_build_loop(
    pyramid,
    should_abort: Callable[[], bool] | None,
    uid: int,
    total_levels: int,
    progress_callback=None,
    target_level: int | None = None,
):
    """Worker body: build levels until complete, aborted, or the demand target lands.

    Phase 5 idle between levels (let event loop breathe) is preserved.
    ``target_level=None`` is the eager path (unchanged). A demand
    ``target_level=k`` bounds the same loop: it never starts when
    ``is_level_built(k)`` holds and stops after the landing level, which
    is emitted with ``complete=True`` (shared toast routing finishes)
    even though the pyramid is incomplete. Never ``build_all`` past k.
    """
    import time

    def _target_ready() -> bool:
        if target_level is None:
            return False
        try:
            return bool(pyramid.is_level_built(int(target_level)))
        except Exception:
            return False

    while not _target_ready() and pyramid.build_next_level(should_abort=should_abort):
        try:
            complete = bool(pyramid.is_complete())
        except Exception:
            complete = False
        if _target_ready():
            complete = True
        if progress_callback is not None:
            progress_callback((uid, pyramid.level_count, total_levels, complete))
        if _target_ready():
            break
        # idle between levels: yield to UI / other workers
        if not complete:
            try:
                time.sleep(0.002)
            except Exception:
                pass
            if should_abort is not None and should_abort():
                break
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
        self._pyramid_toast_live: dict[int, bool] = {}
        # uid -> toast_live pinned at start_build time. A preview-tier race
        # (decode still in flight) must never finish/dismiss a toast whose
        # real decode is still pending — the pin carries the start-time
        # decision to the async finish paths below.

    # --- compat properties (tests peek at controller sets) ---
    @property
    def pyramid_builds(self) -> set[int]:
        return self._pyramid_builds

    @property
    def pyramid_toast_slot(self) -> dict[int, int]:
        return self._pyramid_toast_slot

    @property
    def pyramid_toast_live(self) -> dict[int, bool]:
        """Pinned per-uid toast liveness (mirrors ``pyramid_toast_slot``)."""
        return self._pyramid_toast_live

    # Back-compat alias used by IC ( _loading_toast_uid_slot )
    @property
    def loading_toast_uid_slot(self) -> dict[int, int]:
        return self._pyramid_toast_slot

    # --- core ---

    def _resolve_get_pyramid(self):
        if self._get_pyramid is not None:
            return self._get_pyramid
        try:
            from engine.store.pyramid_registry import ensure_pyramid

            return ensure_pyramid
        except Exception:
            return lambda _s: None

    def _resolve_estimate(self):
        if self._estimate_levels is not None:
            return self._estimate_levels
        try:
            from engine.store.pyramid_pixel_store import estimate_total_levels

            return estimate_total_levels
        except Exception:
            return lambda w, h: 1

    def start_build(
        self,
        store,
        *,
        slot_id: int | None = None,
        toast_live: bool = True,
        should_abort: Callable[[], bool] | None = None,
        on_level_ready: Callable[[Any], None] | None = None,
    ) -> bool:
        """Start a pyramid build for *store*; returns True iff a worker was started.

        The uid->slot mapping is recorded whenever *slot_id* is given, so a
        later ``complete`` always finds its toast — even if the decode was
        still in flight at start time (``toast_live=False``) and lands after
        the pyramid. Progress bumps and skip-path finishes honor *toast_live*
        (a preview-tier race must not finish a toast whose real decode is
        still pending). Skipped cases with a live toast finish it via the
        toast coordinator instead of leaving it stuck at "pyramid started".
        """
        from engine.cache.image_identity import image_uid

        get_pyramid = self._resolve_get_pyramid()

        # early toast finish helper (live toasts only — a preview-tier race
        # must not finish a toast whose real decode is still pending)
        def _finish_toast_if_needed():
            if slot_id is not None and toast_live and self._toast is not None:
                try:
                    self._toast.finish(slot_id)
                except Exception:
                    pass

        pyramid = get_pyramid(store)
        if pyramid is None:
            logger.debug(
                "[Pyramid] skip build: no pyramid for store %sx%s",
                getattr(store, "width", -1),
                getattr(store, "height", -1),
            )
            _finish_toast_if_needed()
            return False
        if pyramid.is_complete():
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
            logger.debug("[Pyramid] skip build: already in flight (uid=%s)", uid)
            _finish_toast_if_needed()
            return False

        thread_pool = self._get_thread_pool()
        if thread_pool is None:
            _finish_toast_if_needed()
            return False

        estimate = self._resolve_estimate()
        try:
            total_levels = estimate(store.width, store.height)
        except Exception:
            total_levels = 1

        self._pyramid_builds.add(uid)
        if slot_id is not None:
            # Always map (keep-first): a later complete must find its toast
            # even when the decode was still in flight at start time. Two
            # slots sharing one store keep the first mapping (same as before
            # for the second slot — rare, documented). The toast_live pin
            # follows the same keep-first rule so the finish/dismiss paths
            # below honor the first starter's liveness decision.
            self._pyramid_toast_slot.setdefault(uid, slot_id)
            self._pyramid_toast_live.setdefault(uid, toast_live)
            if toast_live and self._toast is not None:
                try:
                    self._toast.bump_pyramid_started(slot_id)
                except Exception:
                    pass

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

    def demand_level(
        self,
        store,
        k: int,
        *,
        slot_id: int | None = None,
        toast_hook: Callable[[str], None] | None = None,
        should_abort: Callable[[], bool] | None = None,
        on_ready: Callable[[Any], None] | None = None,
    ) -> bool:
        """Demand-build pyramid level *k* (lazy LOD entry, QL-trigger shape).

        Bounded sibling of :meth:`start_build`: the worker runs the shared
        loop with ``target_level=k`` — builds only until ``is_level_built(k)``
        (never ``build_all``); the landing payload carries ``complete=True``
        so the shared toast routing finishes. Engine primitives verbatim;
        walk staleness honored per level via *should_abort*. True iff kicked
        or already built (no worker then); False on bad k, pre-abort, no
        pyramid, in-flight, no pool, or start failure. Same coordinator toast
        routing (bump/progress/finish/dismiss); *toast_hook* is an additive
        ``"started"|"progress"|"ready"|"aborted"`` observer. Fan-out runs
        :meth:`on_level_ready` first, then *on_ready*.
        """
        from engine.cache.image_identity import image_uid

        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            return False
        if should_abort is not None:
            try:
                if bool(should_abort()):
                    return False
            except Exception:
                return False

        def _notify(event: str) -> None:
            if toast_hook is not None:
                try:
                    toast_hook(event)
                except Exception:
                    pass

        get_pyramid = self._resolve_get_pyramid()
        pyramid = get_pyramid(store)
        if pyramid is None:
            return False
        try:
            already = bool(pyramid.is_level_built(k))
        except Exception:
            return False
        if already:
            if slot_id is not None and self._toast is not None:
                try:
                    self._toast.finish(slot_id)
                except Exception:
                    pass
            _notify("ready")
            return True

        uid = image_uid(store)
        if uid in self._pyramid_builds:
            return False

        thread_pool = self._get_thread_pool()
        if thread_pool is None:
            return False

        estimate = self._resolve_estimate()
        try:
            total_levels = estimate(store.width, store.height)
        except Exception:
            total_levels = 1

        self._pyramid_builds.add(uid)
        if slot_id is not None:
            self._pyramid_toast_slot.setdefault(uid, slot_id)
            self._pyramid_toast_live.setdefault(uid, True)
            if self._toast is not None:
                try:
                    self._toast.bump_pyramid_started(slot_id)
                except Exception:
                    pass
        _notify("started")

        # capture should_abort; default is never abort
        abort = should_abort if should_abort is not None else lambda: False

        worker = GenericWorker(_pyramid_build_loop, pyramid, abort, uid, total_levels)
        worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
        worker.kwargs["target_level"] = int(k)

        def _fanout(payload) -> None:
            try:
                self.on_level_ready(payload)
            except Exception:
                pass
            done = isinstance(payload, tuple) and len(payload) == 4 and bool(payload[3])
            _notify("ready" if done else "progress")
            if on_ready is not None:
                try:
                    on_ready(payload)
                except Exception:
                    pass

        worker.signals.partial_result.connect(_fanout)

        def _demand_finished(finished_uid: int = uid) -> None:
            stuck = self._pyramid_toast_slot.get(finished_uid)
            self._on_build_finished(finished_uid)
            if stuck is not None:
                _notify("aborted")

        worker.signals.finished.connect(_demand_finished)
        try:
            thread_pool.start(worker)
        except Exception:
            self._on_build_finished(uid)
            return False
        return True

    def _on_build_finished(self, uid: int) -> None:
        """Worker done: drop the in-flight mark; dismiss a stuck toast mapping.

        If the uid→slot mapping is still present here, no complete payload
        ever arrived (abort / stalled loop) — dismiss the slot's toast so it
        cannot hang forever. The dismiss honors the start-time toast_live
        pin: a non-live build (preview-tier race, decode still pending)
        drops its mapping without touching the decode's toast.
        """
        self._pyramid_builds.discard(uid)
        live = self._pyramid_toast_live.pop(uid, True)
        slot_id = self._pyramid_toast_slot.pop(uid, None)
        if slot_id is not None and live and self._toast is not None:
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
            return
        if self._toast is None:
            if complete:
                self._pyramid_toast_slot.pop(uid, None)
                self._pyramid_toast_live.pop(uid, None)
            return
        if complete:
            # Pinned liveness: a non-live build (preview-tier race) must not
            # finish a toast whose real decode is still pending — the decode
            # path owns that toast. Drop the mapping either way.
            live = self._pyramid_toast_live.pop(uid, True)
            self._pyramid_toast_slot.pop(uid, None)
            if not live:
                return
            try:
                self._toast.finish(slot_id)
            except Exception:
                pass
        else:
            if not self._pyramid_toast_live.get(uid, True):
                return
            fraction = level_count / max(total_levels, 1)
            percent = PYRAMID_START_PROGRESS + int(fraction * (100 - PYRAMID_START_PROGRESS))
            try:
                self._toast.set_progress(slot_id, percent)
            except Exception:
                pass
