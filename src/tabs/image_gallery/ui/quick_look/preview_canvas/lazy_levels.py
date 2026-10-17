"""Quick-look canvas: demand-built lazy levels (sharp zoom).

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).

Audit-Meta: pattern=thin-owner-target size=exempt reason="one demand-pyramid lifecycle: dwell/zoom trigger, lazy level target, abort + resume share one canvas generation"
"""

from __future__ import annotations

import logging

# Decode caps owned by services/decode_policy.py (single home).
from tabs.image_gallery.services.decode_policy import (
    QL_FULL_EDGE_CAP as _QL_FULL_EDGE_CAP,
    exceeds_edge,
)

from .source import _ql_decode_full_store

logger = logging.getLogger("ImproveImgSLI")

# Dwell pre-warm: an item continuously shown past this window builds the
# needed levels even at zoom 1.0 (singleShot, generation-guarded -- a walk
# retires the timer before it can fire).
_QL_DWELL_MS = 1200


# -- demand-built lazy levels (sharp zoom) ------------------------------------


def note_ql_source(self, path) -> None:
    """Remember the source path for a demand full-res build; arm dwell.

    Called by the host after ``set_source`` (both memo-hit and miss
    paths). Arms the dwell singleShot: an item continuously shown past
    ``_QL_DWELL_MS`` pre-warms the pyramid even at zoom 1.0. Walks
    retire the timer via the ``_ql_gen`` bump in
    ``set_source``/``clear_source``. Never raises.
    """
    try:
        try:
            p = str(path or "")
        except Exception:
            p = ""
        if not p:
            return
        try:
            self._ql_source_path = p
            gen = int(getattr(self, "_ql_gen", 0) or 0)
        except Exception:
            return
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(int(_QL_DWELL_MS), lambda _g=gen: self._ql_on_dwell(_g))
        except Exception:
            pass
    except Exception:
        pass


def _ql_on_dwell(self, gen) -> None:
    """Dwell-timer fire: pre-warm the pyramid iff the item is still shown."""
    try:
        try:
            live = int(getattr(self, "_ql_gen", 0) or 0) == int(gen)
        except Exception:
            live = False
        if not live:
            return  # walked away — never build on plain walks.
        self._maybe_demand_build("dwell")
    except Exception:
        pass
    try:  # staged tiled kick shares the dwell gate (no second timer).
        self._fire_ql_tiled_pending()
    except Exception:
        pass


def _fire_ql_tiled_pending(self) -> None:
    """Fire the staged tiled full-store kick (dwell/zoom trigger).

    The host stages exactly one pending kick per show
    (``preview_canvas_host._arm_tiled_dwell``); dwell fires it here and
    wheel-zoom past 1.0 fires it eagerly from ``wheelEvent``. Consumed
    exactly once: walks retire it via ``_drop_ql_demand`` (called from
    ``set_source``/``clear_source``), so a pending that exists is always
    for the live item and needs no extra generation check. A tiled memo
    hit never stages (installed synchronously at show). Never raises.
    """
    try:
        try:
            pending = getattr(self, "_ql_tiled_pending", None)
            self._ql_tiled_pending = None
        except Exception:
            return
        if not isinstance(pending, dict):
            return
        try:
            ref = pending.get("overlay")
            overlay = ref() if ref is not None else None
        except Exception:
            overlay = None
        if overlay is None:
            return
        try:
            path_s = str(pending.get("path") or "")
            key = pending.get("key")
        except Exception:
            return
        if not path_s:
            return
        try:
            from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                _populate_tiled_source,
            )

            _populate_tiled_source(overlay, self, path_s, key)
        except Exception:
            pass
    except Exception:
        pass


def _drop_ql_demand(self) -> None:
    """Abort in-flight demand work + close canvas-private full materials.

    The generation bump retires dwell timers, decode workers (their
    result/finish slots see a stale gen and close the decoded store)
    and level builds (``should_abort``). The full store + derived
    pyramid are canvas-private (never memoized) so they close here —
    walk keeps COARSE memos open, overlay-close drops those via the
    host. Never raises.
    """
    try:
        try:
            self._ql_gen = int(getattr(self, "_ql_gen", 0) or 0) + 1
        except Exception:
            pass
        for _attr in ("_ql_decoding",):
            try:
                setattr(self, _attr, False)
            except Exception:
                pass
        for _attr in ("_ql_coarse_only",):
            try:
                setattr(self, _attr, False)
            except Exception:
                pass
        try:
            self._ql_source_path = None
        except Exception:
            pass
        try:  # a walk/item-change drops the staged tiled kick with it.
            self._ql_tiled_pending = None
        except Exception:
            pass
        try:
            self._ql_probe_path = None
            self._ql_probe_dims = None
        except Exception:
            pass
        try:
            pyr = getattr(self, "_ql_pyramid", None)
            self._ql_pyramid = None
        except Exception:
            pyr = None
        try:
            full = getattr(self, "_ql_full_store", None)
            self._ql_full_store = None
        except Exception:
            full = None
        try:
            if pyr is not None:
                pyr.close()  # derived levels only; base closes below.
        except Exception:
            pass
        try:
            if full is not None:
                full.close()
        except Exception:
            pass
        try:
            self._frame_key = None
        except Exception:
            pass
    except Exception:
        logger.debug("QuickLook preview: drop demand failed open", exc_info=True)


def _ql_coordinator_lazy(self):
    """Shared PyramidBuildCoordinator for this canvas (no second builder)."""
    try:
        coord = getattr(self, "_ql_coord", None)
        if coord is not None:
            return coord
        from PySide6.QtCore import QThreadPool

        from engine.pyramid.coordinator import PyramidBuildCoordinator

        coord = PyramidBuildCoordinator(
            get_thread_pool=lambda: QThreadPool.globalInstance(),
            toast_coordinator=None,
            get_pyramid=(
                lambda store, _self=self: getattr(_self, "_ql_pyramid", None)
                if store is getattr(_self, "_ql_full_store", None)
                else None
            ),
            request_view_update=lambda _self=self: _self._ql_on_level(None),
            invalidate_render=None,
        )
        self._ql_coord = coord
        return coord
    except Exception:
        return None


def _ql_demand_service_lazy(self):
    """Shared ``PyramidDemandService`` for this canvas (decode + levels).

    Owns the QL demand policy (``cap_edge=_QL_FULL_EDGE_CAP``,
    ``settle=True``) so the decode cap and the view's hold policy come
    from ONE declaration. QL uses the service's decode + ``levels_sequence``
    + policy (not ``ensure_level``), so it is constructed with no
    coordinator: the build coordinator is still created lazily only when a
    live decode actually starts a level build (``_on_ql_full_ready``), so a
    superseded walk leaves ``_ql_coord`` unset. Never raises.
    """
    try:
        svc = getattr(self, "_ql_demand_svc", None)
        if svc is not None:
            return svc
        from engine.cache.pyramid_demand import DemandPolicy, PyramidDemandService

        svc = PyramidDemandService(
            coordinator=None,
            policy=DemandPolicy(cap_edge=_QL_FULL_EDGE_CAP, settle=True),
        )
        self._ql_demand_svc = svc
        return svc
    except Exception:
        return None


def _ql_abort_fn(self, full, gen):
    """Abort predicate for decode + level workers (generation-wired, lazy).

    Aborts when the walk superseded the build (``_ql_gen``), when the
    full store closed under it — or when the needed level landed: the
    coordinator loop checks this between levels, so a build started
    for need ``k`` stops exactly at ``k`` instead of running to
    complete (GIMP-style lazy levels, never ``build_all``). The need
    is read live (``_ql_need``) so a zoom-out mid-build narrows the
    target and the next wheel tick resumes a zoom-in. Never raises.
    """

    def _abort(_s=full, _g=int(gen)):
        try:
            if int(getattr(self, "_ql_gen", 0) or 0) != int(_g):
                return True  # walk/item-change superseded this build.
        except Exception:
            return True
        try:
            if not bool(_s.is_open):
                return True
        except Exception:
            return True
        try:
            need = int(getattr(self, "_ql_need", 0) or 0)
            if need <= 0:
                return True  # view no longer needs levels — stop here.
            pyr = getattr(self, "_ql_pyramid", None)
            if pyr is not None and bool(pyr.is_level_built(need)):
                return True  # lazy target landed — stop here.
        except Exception:
            pass
        return False

    return _abort


def _ql_fb_estimate(self) -> tuple[int, int]:
    """Framebuffer size for the need computation (last raster, else widget)."""
    try:
        last = getattr(self, "_last_fb", None)
        if last is not None and int(last[0]) > 0 and int(last[1]) > 0:
            return int(last[0]), int(last[1])
    except Exception:
        pass
    try:
        return max(1, int(self.width())), max(1, int(self.height()))
    except Exception:
        return 1, 1


def _ql_needed_level(self, fb_w: int, fb_h: int, full_w: int, full_h: int, zoom) -> int:
    """Levels needed for the CURRENT view (0 = coarse suffices). Never raises.

    Shared LOD all the way down: ``select_level`` over the full
    ``estimate_total_levels`` count with display-px per full-res px —
    the same inputs the raster's ``best_pixels`` uses, so the target
    and the sampler can never disagree about which level is which.
    """
    try:
        from engine.cache.lod import demand_level, dest_scale_fit
        from engine.store.pyramid_pixel_store import estimate_total_levels

        fw, fh = int(full_w), int(full_h)
        if fw <= 0 or fh <= 0:
            return 0
        try:
            z = float(zoom)
        except Exception:
            return 0
        dest_scale = dest_scale_fit((fb_w, fb_h), (fw, fh), z)
        return int(demand_level(dest_scale, estimate_total_levels(fw, fh)))
    except Exception:
        return 0


def _ql_resume_build(self, full, gen) -> bool:
    """Demand-build the newly needed level over an open full store.

    Recomputes the need from the CURRENT zoom (a deeper zoom widened
    the target while the decode was in flight); already-built targets
    are a no-op (built levels stay, never rebuilt). Never raises.
    """
    try:
        try:
            z = float(getattr(self, "_zoom", 1.0))
        except Exception:
            z = 1.0
        try:
            fw, fh = full.size
            fb_w, fb_h = self._ql_fb_estimate()
            need = self._ql_needed_level(fb_w, fb_h, fw, fh, z)
        except Exception:
            need = 0
        try:
            self._ql_need = int(need)
        except Exception:
            pass
        if need <= 0:
            return False  # coarse suffices for this view — nothing to do.
        try:
            pyr = getattr(self, "_ql_pyramid", None)
            if pyr is not None and bool(pyr.is_level_built(int(need))):
                return False  # target already built — no rebuild.
        except Exception:
            pass
        coord = self._ql_coordinator_lazy()
        if coord is None:
            return False
        try:
            from engine.cache.image_identity import image_uid

            in_flight = set(getattr(coord, "pyramid_builds", ()) or ())
            if int(image_uid(full)) in in_flight:
                return False  # already building — nothing to do.
        except Exception:
            pass
        return bool(
            coord.start_build(
                full,
                slot_id=None,
                toast_live=False,
                should_abort=self._ql_abort_fn(full, gen),
                on_level_ready=self._ql_on_level,
            )
        )
    except Exception:
        return False


def _maybe_demand_build(self, reason: str = "") -> bool:
    """Kick the background lazy-level build (zoom/dwell only). Never raises.

    Returns True iff a decode worker or level build was started.
    Fast-open is untouched: the coarse store keeps driving frames
    until levels land (each level invalidates the frame cache). Only
    the levels needed for the CURRENT zoom are ever built (lazy,
    GIMP-style); a deeper zoom re-triggers for the newly needed one.
    """
    try:
        try:
            path = str(getattr(self, "_ql_source_path", None) or "")
        except Exception:
            path = ""
        if not path:
            return False
        if bool(getattr(self, "_ql_coarse_only", False)):
            return False
        try:
            live_gen = int(getattr(self, "_ql_gen", 0) or 0)
        except Exception:
            live_gen = 0
        try:
            z = float(getattr(self, "_zoom", 1.0))
        except Exception:
            z = 1.0
        # An existing pyramid: complete → nothing to do; partial →
        # resume only the newly needed level (or no-op when it is
        # built / in flight). Built levels stay, never rebuilt.
        try:
            pyr = getattr(self, "_ql_pyramid", None)
        except Exception:
            pyr = None
        if pyr is not None:
            try:
                valid = bool(pyr.valid)
            except Exception:
                valid = False
            if valid:
                try:
                    if bool(pyr.is_complete()):
                        return False
                except Exception:
                    return False
                full = getattr(self, "_ql_full_store", None)
                if full is not None:
                    try:
                        return bool(self._ql_resume_build(full, live_gen))
                    except Exception:
                        return False
                return False
            try:  # stale pyramid (base closed) — drop derived, re-decode.
                self._ql_pyramid = None
                pyr.close()
            except Exception:
                pass
            try:
                full = getattr(self, "_ql_full_store", None)
                self._ql_full_store = None
                if full is not None:
                    full.close()
            except Exception:
                pass
        if bool(getattr(self, "_ql_decoding", False)):
            # Decode in flight: refresh the lazy target so the landing
            # builds what the CURRENT zoom needs, then wait for it.
            try:
                _dims = getattr(self, "_ql_probe_dims", None)
                if _dims is not None and int(_dims[0]) > 0 and int(_dims[1]) > 0:
                    _fb_w, _fb_h = self._ql_fb_estimate()
                    self._ql_need = int(
                        self._ql_needed_level(_fb_w, _fb_h, _dims[0], _dims[1], z)
                    )
            except Exception:
                pass
            return False
        # Cheap dims probe (reader header only, no decode), cached per
        # source path so wheel storms don't re-open the file per tick:
        # huge or untracked sources stay coarse-only — no behavior change.
        try:
            if getattr(self, "_ql_probe_path", None) != path:
                from tabs.image_gallery.ui.quick_look.preview import _fast_image_size

                self._ql_probe_dims = _fast_image_size(path)
                self._ql_probe_path = path
            dims = getattr(self, "_ql_probe_dims", None)
        except Exception:
            dims = None
        try:
            ok_dims = dims is not None and int(dims[0]) > 0 and int(dims[1]) > 0
        except Exception:
            ok_dims = False
        try:
            over = (not ok_dims) or exceeds_edge(dims[0], dims[1], _QL_FULL_EDGE_CAP)
        except Exception:
            over = True
        if over:
            try:
                self._ql_coarse_only = True
            except Exception:
                pass
            return False
        # Lazy gate: the coarse suffices for this view → no decode at
        # all (transient: a deeper zoom re-evaluates, no flag set).
        try:
            _fb_w, _fb_h = self._ql_fb_estimate()
            _need = self._ql_needed_level(_fb_w, _fb_h, dims[0], dims[1], z)
        except Exception:
            _need = 0
        try:
            self._ql_need = int(_need)
        except Exception:
            pass
        if _need <= 0:
            return False
        try:  # spill dir on the GUI thread — the worker stays Qt-free.
            from engine.store.tiled_pixel_store import resolve_pixel_spill_dir

            tmp_dir = resolve_pixel_spill_dir()
        except Exception:
            tmp_dir = None
        try:
            from PySide6.QtCore import QThreadPool

            from sli_ui_toolkit.workers import GenericWorker

            pool = QThreadPool.globalInstance()
        except Exception:
            pool = None
        if pool is None:
            return False
        try:
            self._ql_decoding = True
        except Exception:
            pass
        try:
            svc = self._ql_demand_service_lazy()
            if svc is not None:
                # Route the demand decode through the shared service
                # (explicit cap = _QL_FULL_EDGE_CAP).
                worker = GenericWorker(
                    svc.decode_full,
                    path,
                    cap_edge=_QL_FULL_EDGE_CAP,
                    tmp_dir=tmp_dir,
                )
            else:
                worker = GenericWorker(_ql_decode_full_store, path, tmp_dir)
            worker.signals.result.connect(
                lambda store, _g=live_gen: self._on_ql_full_ready(store, _g)
            )
            worker.signals.finished.connect(
                lambda _g=live_gen: self._on_ql_decode_finished(_g)
            )
            pool.start(worker)
        except Exception:
            try:
                self._ql_decoding = False
            except Exception:
                pass
            return False
        try:
            logger.debug(
                "QuickLook preview: demand pyramid decode started (%s) path=%s",
                reason or "?",
                path,
            )
        except Exception:
            pass
        return True
    except Exception:
        logger.debug("QuickLook preview: demand trigger failed open", exc_info=True)
        return False


def _on_ql_full_ready(self, store, gen) -> None:
    """GUI-thread decode landing: install full store + start levels."""
    try:
        try:
            import shiboken6

            _valid = shiboken6.isValid(self)
        except Exception:
            _valid = True
        try:
            live = bool(_valid) and int(getattr(self, "_ql_gen", 0) or 0) == int(gen)
        except Exception:
            live = False
        if not live:
            try:  # superseded (walk) — no pyramid materials kept.
                if store is not None:
                    store.close()
            except Exception:
                pass
            return
        try:
            ok = store is not None and bool(store.is_open)
        except Exception:
            ok = False
        if not ok:
            try:
                self._ql_decoding = False
                self._ql_coarse_only = True
            except Exception:
                pass
            return
        try:
            from engine.store.pyramid_pixel_store import PyramidPixelStore

            pyr = PyramidPixelStore(store)
        except Exception:
            try:
                store.close()
            except Exception:
                pass
            try:
                self._ql_decoding = False
                self._ql_coarse_only = True
            except Exception:
                pass
            return
        try:
            self._ql_full_store = store
            self._ql_pyramid = pyr
            self._ql_decoding = False
        except Exception:
            pass
        # Lazy target from the CURRENT zoom + real full dims (the zoom
        # may have moved during the decode); an already-satisfied
        # target starts no worker at all.
        try:
            z = float(getattr(self, "_zoom", 1.0))
        except Exception:
            z = 1.0
        try:
            fw, fh = store.size
            fb_w, fb_h = self._ql_fb_estimate()
            need = self._ql_needed_level(fb_w, fb_h, fw, fh, z)
        except Exception:
            need = 0
        try:
            self._ql_need = int(need)
        except Exception:
            pass
        try:
            satisfied = need <= 0 or bool(pyr.is_level_built(int(need)))
        except Exception:
            satisfied = False
        try:
            coord = None if satisfied else self._ql_coordinator_lazy()
            started = (
                bool(
                    coord.start_build(
                        store,
                        slot_id=None,
                        toast_live=False,
                        should_abort=self._ql_abort_fn(store, gen),
                        on_level_ready=self._ql_on_level,
                    )
                )
                if coord is not None
                else False
            )
        except Exception:
            started = False
        try:
            logger.debug("QuickLook preview: demand pyramid levels started=%s", started)
        except Exception:
            pass
        try:
            self._frame_key = None
            self.update()
        except Exception:
            pass
    except Exception:
        logger.debug("QuickLook preview: full-ready failed open", exc_info=True)


def _on_ql_decode_finished(self, gen) -> None:
    """Decode worker done: failed decodes stay coarse-only (no retry storm)."""
    try:
        try:
            live = int(getattr(self, "_ql_gen", 0) or 0) == int(gen)
        except Exception:
            live = False
        if not live:
            return  # teardown already ran (walk/clear).
        try:
            if getattr(self, "_ql_full_store", None) is not None:
                try:
                    self._ql_decoding = False
                except Exception:
                    pass
                return  # success path — the result slot installed it.
        except Exception:
            pass
        try:
            self._ql_decoding = False
            self._ql_coarse_only = True
        except Exception:
            pass
    except Exception:
        pass


def _ql_on_level(self, payload) -> None:
    """Level landed (any thread): drop the frame cache, repaint. Never raises."""
    try:
        try:
            import shiboken6

            if not shiboken6.isValid(self):
                return
        except Exception:
            pass
        try:
            self._frame_key = None
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
    except Exception:
        pass


def _ql_levels_token(self) -> int:
    """Frame-key addendum: built level count, -1 without a live pyramid."""
    try:
        pyr = getattr(self, "_ql_pyramid", None)
        if pyr is None or not bool(getattr(pyr, "valid", False)):
            return -1
        return int(getattr(pyr, "level_count", 0) or 0)
    except Exception:
        return -1
