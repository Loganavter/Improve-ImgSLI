"""Quick Look single-quad GPU preview — gallery tab, deliberately canvas-light.
Audit-Meta: pattern=thin-owner-target size=exempt reason="one QRhiWidget lifecycle: plan/raster/zoom-pan/demand-pyramid share one frame entry + generation"

``QuickLookCanvasWidget`` is a minimal ``QRhiWidget`` showing one
aspect-fit image quad. It is intentionally far lighter than the compare
tabs: no scene tree, no feature passes, no gestures, no overlays, no
labels.

Seam rules (frozen with host/tests): one quad from _active_composition
via the shared applicator only; pixels from the caller-provided store
 sampled verbatim through ``PyramidPixelStore.best_pixels`` (bounded
 ``read_array`` only — never ``qimage_from_pixel_source``, never a host
 upload cache, never a full-frame materialize); GPU objects belong to
 TexturedOverlayShell only. The host hands this widget a bounded coarse
 store (``preview_canvas_host._coarse_store_for``); a miss samples to
 None and the frame is skipped. Fail open; previewFailed → QLabel
 fallback, firstFramePresented (settled present + restack, MC parity)
 → cover drop.

Demand-built LAZY levels (sharp zoom): the coarse store above still
drives the first frame exactly as before; on zoom>1.0 or dwell
(``note_ql_source`` arms the dwell timer — never on plain walks) only
the levels needed for the CURRENT zoom are built (``best_level_for_scale``
target, ``build_next_level`` until it lands or the walk aborts it)
through the shared ``tabs._shared.pyramid.PyramidBuildCoordinator`` (no
second builder, GIMP-style: built levels stay, deeper zooms add more).
The zoomed frame then samples the best BUILT level through
``PyramidPixelStore.best_pixels`` (shared ``select_level`` LOD) instead
of CPU-upscaling the coarse; unbuilt levels hold the coarse frame until
they land (``best_pixels`` fails closed to None).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QRhiDepthStencilClearValue
from PySide6.QtWidgets import QRhiWidget, QSizePolicy

from engine.frame.present import begin_source, note_presented
from engine.gpu.tiled_image_view import (
    SingleImageTiledView,
    TiledImageSource,
    TiledImageView,
    load_tiled_image_shader,
)
from engine.overlay import TexturedOverlayBinding, TexturedOverlayShell
from engine.store.tiled_pixel_store import pixel_source_size
from ui.canvas_infra.rhi.rhi_backend import configure_rhi_widget
from ui.canvas_presentation.composition import LayerNode
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan
from tabs.image_gallery.ui.quick_look.preview_canvas_host import settle_first_frame

logger = logging.getLogger("ImproveImgSLI")

# Identity clip matrix for the fullscreen shell quad (the preview has no
# viewport transform — aspect-fit is baked into the uploaded raster).
_IDENTITY_CLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

_CLEAR_OPAQUE = QColor(0, 0, 0, 255)

# No-present watchdog: a canvas that shows no frame within this window is
# presumed broken (dead RHI, missing shaders) and must yield to QLabel —
# a transparent widget shows the windows behind it as "garbage".
_NO_FRAME_TIMEOUT_MS = 1500

# Host decode cap: the letterbox only needs framebuffer resolution; a full
# 40k decode here would repeat the QLabel-path OOM this canvas replaces.
_DECODE_EDGE_CAP = 2048

# Demand full-res cap: the background full store is disk-backed (memmap),
# but still bounded — 4096^2x4B = 64 MiB spill + ~1/3 pyramid overhead,
# and 4x linear headroom over the 1024 coarse so wheel zoom stays sharp
# to ~4x. Huge/untracked sources fail open to coarse-only (no behavior
# change for them) — same thinking as _PREVIEW_FULL_DECODE_EDGE.
_QL_FULL_EDGE_CAP = 4096

# Dwell pre-warm: an item continuously shown past this window builds the
# needed levels even at zoom 1.0 (singleShot, generation-guarded — a walk
# retires the timer before it can fire).
_QL_DWELL_MS = 1200


def _ql_decode_full_store(path, tmp_dir=None):
    """Background full-res decode for the demand pyramid (worker thread).

    Pure Python + PIL/pyvips + memmap — no Qt: the spill dir is resolved
    on the GUI thread and passed in as ``tmp_dir``. Enforces
    ``_QL_FULL_EDGE_CAP`` post-decode (dims probes can lie); huge sources
    fail open to None (coarse-only, no behavior change). Never raises.
    """
    try:
        from engine.store.tiled_pixel_store import TiledPixelStore

        try:
            store = TiledPixelStore.from_path(str(path), tmp_dir)
        except Exception:
            return None
        try:
            w, h = store.size
        except Exception:
            try:
                store.close()
            except Exception:
                pass
            return None
        try:
            if max(int(w), int(h)) > int(_QL_FULL_EDGE_CAP):
                try:
                    store.close()
                except Exception:
                    pass
                return None
        except Exception:
            try:
                store.close()
            except Exception:
                pass
            return None
        return store
    except Exception:
        return None


def _overlay_shader_dir() -> Path | None:
    """Shared quad shaders by path (no cross-tab import); None = inert."""
    try:
        tabs = Path(__file__).resolve().parents[3]
    except Exception:
        return None
    candidates = (
        tabs / "multi_compare" / "shaders" / "qrhi",
        tabs / "image_compare" / "canvas" / "shaders" / "overlay",
    )
    for cand in candidates:
        try:
            if (cand / "overlay.vert.qsb").is_file() and (cand / "overlay.frag.qsb").is_file():
                return cand
        except OSError:
            continue
    return None




class QuickLookCanvasWidget(QRhiWidget):
    """Minimal single-quad GPU preview (set_source/clear_source + repaint)."""

    previewFailed = Signal()
    firstFramePresented = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        self._store = None
        self._active_composition = None
        self._active_render_plan = None
        self._shell = TexturedOverlayShell()
        self._shell_ready = False
        self._frame_key = None
        self._frame_bytes: tuple[int, int, bytes] | None = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_last = None
        self._frame_ok = False
        self._watchdog_armed = False
        self._watchdog_gen = 0
        self._ql_gen = 0
        self._ql_source_path = None
        self._ql_full_store = None
        self._ql_pyramid = None
        self._ql_decoding = False
        self._ql_coarse_only = False
        self._ql_coord = None
        self._ql_need = 0
        self._ql_probe_path = None
        self._ql_probe_dims = None
        self._last_fb = None
        # Tiled single-source path (additive): a full TiledPixelStore drawn
        # from texture-array tiles instead of the single-quad raster. The
        # raster/shell path stays the pre-first-frame / fail-open surface.
        self._tiled_source = None
        self._tile_renderer = None
        self._tile_sampler = None
        try:
            self._present_debt = begin_source(None)
        except Exception:
            self._present_debt = None
        try:
            configure_rhi_widget(self)
        except Exception:
            logger.debug("QuickLook preview: RHI setup failed; staying inert", exc_info=True)

    # -- source lifetime --------------------------------------------------------

    def set_source(self, store) -> None:
        """Adopt ``store`` (closes the previous one it owns). Never raises.

        Ownership: a held store that is a live memo entry belongs to the
        host overlay's cache, not to this canvas — replacing/clearing it
        drops the ref WITHOUT closing (the cache closes it on
        evict/replace/overlay-release). Only privately-built (uncached)
        held stores are closed here. Fail-open: without a probe every held
        store closes as before.
        """
        try:
            _ql_changed = store is not self._store
        except Exception:
            _ql_changed = True
        try:
            if store is self._store:
                self._refresh_plan()
            else:
                self._close_held_store()
                self._store = store
                self._frame_key = None
                self._frame_bytes = None
                self._refresh_plan()
        except Exception:
            logger.debug("QuickLook preview: set_source failed open", exc_info=True)
        try:
            self._frame_ok = False
            self._settle_pumped = False
            self._settle_scheduled = False
            self._zoom = 1.0
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._drag_last = None
            self._frame_key = None
            try:
                from tabs.image_gallery.ui.quick_look.preview_watchdog import next_gen
                # Renews canvas._present_debt (new generation) via begin_source.
                gen = next_gen(self)
            except Exception:
                gen = None
            self._arm_watchdog(gen)
        except Exception:
            pass
        try:
            # A new coarse item retires the previous demand pyramid (its
            # full store sampled a different source); a re-set of the SAME
            # store keeps it (revisit fast path). Never raises.
            if _ql_changed:
                self._drop_ql_demand()
        except Exception:
            pass
        try:
            # A changed coarse item also invalidates any tiled full source
            # (it belonged to the previous item); the host re-registers the
            # new one via set_tiled_source right after.
            if _ql_changed:
                self.clear_tiled_source()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _arm_watchdog(self, gen=None) -> None:
        """Yield to QLabel when no frame presents in time (never raises).

        Generation-guarded (see ``preview_watchdog``): a pending timer
        from a previous source never kills the new one.
        """
        try:
            from tabs.image_gallery.ui.quick_look.preview_watchdog import arm_watchdog
            arm_watchdog(self, gen)
        except Exception:
            pass

    def _on_watchdog(self, expected_gen=None) -> None:
        """Fire a pending no-frame timer (never raises)."""
        try:
            from tabs.image_gallery.ui.quick_look.preview_watchdog import fire_watchdog
            fire_watchdog(self, expected_gen)
        except Exception:
            pass

    def clear_source(self) -> None:
        """Release the held store + composition. Never raises.

        Ownership (see ``set_source``): a memoized held store is dropped,
        never closed; a privately-built one is closed. Already-closed held
        stores are never closed twice.
        """
        try:
            from tabs.image_gallery.ui.quick_look.preview_watchdog import invalidate
            # Renews canvas._present_debt (retires the pending timer) + disarms.
            invalidate(self)
        except Exception:
            pass
        try:
            self._close_held_store()
            self._active_composition = None
            self._active_render_plan = None
            self._frame_key = None
            self._frame_bytes = None
        except Exception:
            logger.debug("QuickLook preview: clear_source failed open", exc_info=True)
        try:
            # Retire the tiled full store FIRST: it may point at the same
            # canvas-private full store _drop_ql_demand is about to close.
            self.clear_tiled_source()
        except Exception:
            pass
        try:
            # Walk/item-change retires the demand build (generation bump
            # aborts decode + levels) and closes the canvas-private full
            # materials. Coarse memos stay open (host cache owns them).
            self._drop_ql_demand()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _close_held_store(self) -> None:
        """Close the held store this canvas owns — never a memo, never twice.

        The host installs ``_ql_is_memo`` (see ``preview_canvas_host``): a
        held store that is a live cache entry is owned by the memo cache and
        is dropped WITHOUT closing. An already-closed held store is dropped
        without a second ``close()`` (``is_open`` guard). Only an open,
        privately-built held store is closed here. Never raises.
        """
        held = self._store
        self._store = None
        if held is None:
            return
        try:
            probe = getattr(self, "_ql_is_memo", None)
            if callable(probe) and bool(probe(held)):
                return  # memoized — the cache owns it, keep open.
        except Exception:
            pass
        try:
            if not bool(getattr(held, "is_open", True)):
                return  # already closed — never double-close.
        except Exception:
            pass
        try:
            held.close()
        except Exception:
            pass

    # -- tiled single-source path (additive) --------------------------------------

    def set_tiled_source(self, key, store) -> None:
        """Register a full ``TiledPixelStore`` to draw from array tiles.

        Additive: the raster/cover path keeps serving until this tiled
        source is *fully covered* (every visible tile resident); a missing
        slot fails closed per tile, so a half-uploaded grid never
        substitutes a neighbor and never surfaces as a transparent frame.
        Never raises.
        """
        try:
            self._tiled_source = (key, store)
            self._tile_bound_source = None
        except Exception:
            self._tiled_source = None
            return
        try:
            self._ensure_tile_renderer()
        except Exception:
            logger.debug("QuickLook preview: tile renderer setup failed open", exc_info=True)
        try:
            self.update()
        except Exception:
            pass

    def clear_tiled_source(self) -> None:
        """Drop the tiled source + its GPU tiles (walk/close). Never raises."""
        try:
            self._tiled_source = None
            self._tile_bound_source = None
        except Exception:
            pass
        try:
            renderer = self._tile_renderer
            if renderer is not None:
                renderer.clear_source()
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _sampler_for_tiles(self, name):
        """Lazy ``linear`` sampler for the tile-array SRB (owned here)."""
        try:
            if name != "linear":
                return None
            existing = self._tile_sampler
            if existing is not None:
                return existing
            rhi = self.rhi()
            if rhi is None:
                return None
            from PySide6.QtGui import QRhiSampler

            sampler = rhi.newSampler(
                QRhiSampler.Filter.Linear,
                QRhiSampler.Filter.Linear,
                QRhiSampler.Filter.Linear,
                QRhiSampler.AddressMode.ClampToEdge,
                QRhiSampler.AddressMode.ClampToEdge,
            )
            sampler.setName(b"ql-linear-sampler")
            if not sampler.create():
                return None
            self._tile_sampler = sampler
            return sampler
        except Exception:
            return None

    def _ensure_tile_renderer(self):
        """Construct (once) + bind the engine tiled view to the held source.

        The renderer is ``engine.gpu.tiled_image_view.SingleImageTiledView``;
        QL supplies only its RHI/sampler callables, the engine shader loader
        and the ``ql`` name prefix. Binds ``set_source`` only when the
        (key, store) identity actually changed since the last bind —
        rebinding every frame would drop and re-register the whole tile grid
        (a permanent clear/re-upload loop).
        """
        try:
            if self.rhi() is None:
                return None
            renderer = self._tile_renderer
            if renderer is None:
                renderer = SingleImageTiledView(
                    rhi_getter=lambda: self.rhi(),
                    sampler_getter=self._sampler_for_tiles,
                    load_shader=load_tiled_image_shader,
                    name_prefix="ql",
                )
                self._tile_renderer = renderer
            source = self._tiled_source
            if source is not None:
                key, store = source
                if store is not None:
                    bound = getattr(self, "_tile_bound_source", None)
                    is_bound = (
                        bound is not None
                        and bound[0] is key
                        and bound[1] is store
                    )
                    if not is_bound:
                        renderer.set_source(TiledImageSource(key=key, store=store))
                        self._tile_bound_source = (key, store)
            return renderer
        except Exception:
            logger.debug("QuickLook preview: tile renderer ensure failed open", exc_info=True)
            return None

    def _destroy_tile_renderer(self) -> None:
        """Release the tile renderer + sampler (never raises)."""
        try:
            renderer = self._tile_renderer
            self._tile_renderer = None
            self._tile_bound_source = None
            if renderer is not None:
                renderer.release()
        except Exception:
            pass
        try:
            sampler = self._tile_sampler
            self._tile_sampler = None
            if sampler is not None:
                sampler.destroy()
        except Exception:
            pass

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

            from tabs._shared.pyramid import PyramidBuildCoordinator

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
            from engine.cache.lod import select_level
            from engine.store.pyramid_pixel_store import estimate_total_levels

            fw, fh = int(full_w), int(full_h)
            if fw <= 0 or fh <= 0:
                return 0
            try:
                z = float(zoom)
            except Exception:
                return 0
            dest_scale = min(float(fb_w) / float(fw), float(fb_h) / float(fh)) * z
            return int(select_level(dest_scale, estimate_total_levels(fw, fh)))
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
                over = (not ok_dims) or max(int(dims[0]), int(dims[1])) > int(_QL_FULL_EDGE_CAP)
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

    # -- shared-applicator plan -------------------------------------------------

    def _refresh_plan(self) -> None:
        """Single-LayerNode plan via the shared applicator (only apply path)."""
        try:
            store = self._store
            if store is None:
                self._active_composition = None
                self._active_render_plan = None
                return
            try:
                canvas_w = max(1, int(self.width()))
                canvas_h = max(1, int(self.height()))
            except Exception:
                canvas_w, canvas_h = 1, 1
            plan = CanvasRenderPlan(
                image1=None,
                image2=None,
                source_image1=None,
                source_image2=None,
                source_key=(),
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                render_scene=None,
                overlay_layout=None,
                capture_visible=False,
                capture_color=None,
                guides_enabled=False,
                guides_color=None,
                guides_thickness=0,
                composition_root=LayerNode(layer_id=0, image=store, fit_mode="contain"),
            )
            apply_canvas_render_plan(self, plan)
        except Exception:
            logger.debug("QuickLook preview: plan refresh failed open", exc_info=True)

    # -- QRhiWidget entry points ------------------------------------------------

    def _skip_frame(self, reason: str) -> None:
        """Log a skipped frame at DEBUG (diagnostic-only, never raises)."""
        try:
            logger.debug("QuickLook preview: skip frame (%s)", reason)
        except Exception:
            pass

    def initialize(self, command_buffer) -> None:  # noqa: N802
        try:
            rhi = self.rhi()
            target = self.renderTarget()
            shader_dir = _overlay_shader_dir()
            if rhi is None or target is None or shader_dir is None:
                self._shell_ready = False
                return
            binding = TexturedOverlayBinding(shader_dir=shader_dir, shader_stem="overlay")
            self._shell.mount(rhi, target, binding.shader_dir, binding.shader_stem)
            self._shell_ready = True
        except Exception:
            logger.debug("QuickLook preview: shell mount failed open", exc_info=True)
            self._shell_ready = False
        try:  # additive tiled path: bind a pending full store now the RHI is live
            self._ensure_tile_renderer()
        except Exception:
            logger.debug("QuickLook preview: tile renderer init failed open", exc_info=True)

    def releaseResources(self) -> None:  # noqa: N802
        try:
            self._destroy_tile_renderer()
        except Exception:
            pass
        try:
            self._shell.teardown()
        except Exception:
            pass
        self._shell_ready = False

    def _pump_next_frame(self) -> None:
        """Request one more frame on the GUI loop from any thread.

        ``render()`` runs off the GUI thread, so a direct ``update()``
        here is a cross-thread call and gets lost — fresh widgets
        survived via the first-exposure auto-render, re-shown ones
        (every walk) never presented and died by watchdog (2026-09-28).
        QueuedConnection lands ``update()`` on the GUI loop instead.
        Never raises.
        """
        try:
            from PySide6.QtCore import QMetaObject, Qt as _Qt

            _posted = QMetaObject.invokeMethod(
                self, "update", _Qt.ConnectionType.QueuedConnection
            )
        except Exception:
            _posted = False
        try:
            logger.debug("QuickLook preview: pump posted=%s", bool(_posted))
        except Exception:
            pass
        if not _posted:
            try:
                self.update()
            except Exception:
                pass

    def render(self, command_buffer) -> None:  # noqa: N802
        try:
            if not self._frame_ok:
                try:
                    from PySide6.QtCore import QThread
                    from PySide6.QtWidgets import QApplication as _QA

                    _cur = id(QThread.currentThread())
                    _app = _QA.instance()
                    _gui = id(_app.thread()) if _app is not None else -1
                except Exception:
                    _cur = _gui = -1
                logger.debug(
                    "QuickLook preview: render entered shell_ready=%s visible=%s size=%sx%s pumped=%s gui=%s cur=%s",
                    bool(self._shell_ready),
                    bool(self.isVisible()),
                    self.width(),
                    self.height(),
                    bool(getattr(self, "_settle_pumped", False)),
                    _gui,
                    _cur,
                )
            if not self._shell_ready or command_buffer is None:
                return self._skip_frame("not-ready")
            try:  # letterbox tone = host Window color (QLabel bars parity)
                from PySide6.QtGui import QPalette as _QP

                clear = self.palette().color(_QP.ColorRole.Window)
                clear.setAlpha(255)
            except Exception:
                clear = QColor(_CLEAR_OPAQUE)
            try:
                rhi = self.rhi()
                target = self.renderTarget()
            except Exception:
                return self._skip_frame("no-rhi-target")
            if rhi is None or target is None:
                return self._skip_frame("null-rhi-target")
            try:
                updates = rhi.nextResourceUpdateBatch()
            except Exception:
                return self._skip_frame("no-batch")
            try:
                size = target.pixelSize()
                fb_w = max(1, int(size.width()))
                fb_h = max(1, int(size.height()))
            except Exception:
                fb_w, fb_h = 1, 1
            # Additive tiled path: when a full TiledPixelStore is registered
            # and the RHI is live, draw it from texture-array tiles. It gets
            # its OWN update batch (it may submit uploads even when it draws
            # nothing that frame), so the shell's batch below stays pristine.
            # A frame with no resident tile yet fails open to the raster path.
            try:
                tiled_updates = rhi.nextResourceUpdateBatch()
            except Exception:
                tiled_updates = None
            if tiled_updates is not None and self._render_tiled(
                command_buffer, tiled_updates, target, clear, fb_w, fb_h
            ):
                return
            try:
                self._shell.stage_quad(updates)
                self._shell.stage_clip(updates, _IDENTITY_CLIP)
            except Exception:
                return self._skip_frame("stage-failed")
            frame = self._raster_frame(target)
            if frame is None:
                self._skip_frame("raster-no-frame")
            try:
                self._shell.upload_frame(updates, target, frame)
            except Exception:
                return self._skip_frame("upload-failed")
            try:
                command_buffer.beginPass(
                    target,
                    clear,
                    QRhiDepthStencilClearValue(1.0, 0),
                    updates,
                )
            except Exception:
                return self._skip_frame("begin-failed")
            try:
                if frame is not None:
                    fb_w, fb_h = float(fb_w), float(fb_h)
                    self._shell.draw(command_buffer, width=fb_w, height=fb_h)
                    self._settle_present()
            finally:
                try:
                    command_buffer.endPass()
                except Exception:
                    pass
        except Exception:
            logger.debug("QuickLook preview: frame failed open", exc_info=True)

    def _settle_present(self) -> None:
        """Settle gate (MC parity): present #1 pumps one more frame (the
        compositor may still show the untouched surface); the cover drops
        only on the settled present #2. The count truth lives in
        canvas._present_debt via the frozen engine ledger; _frame_ok stays
        the cover-drop truth until the deferred flush emits. Never raises."""
        try:
            if self._frame_ok:
                return
            try:
                debt = getattr(self, "_present_debt", None)
                if debt is None:
                    debt = begin_source(None)
                    try:
                        self._present_debt = debt
                    except Exception:
                        pass
                from tabs.image_gallery.ui.quick_look.preview_watchdog import (
                    QL_SETTLE_COUNT,
                )

                verdict = note_presented(debt, QL_SETTLE_COUNT)
            except Exception:
                verdict = "waiting"
            if verdict == "pumped":
                self._settle_pumped = True
                self._pump_next_frame()
            elif verdict == "settled":
                settle_first_frame(self)
            # "waiting" → nothing: the emit stays in the deferred flush,
            # never at this counting site.
        except Exception:
            pass

    def _render_tiled(self, command_buffer, updates, target, clear, fb_w, fb_h) -> bool:
        """Drive the tiled source's array draw for this frame.

        Takeover is gated on ``TiledViewResult.covered`` (every visible tile
        resident), never on "at least one tile drawn": while the tile set is
        still streaming the caller keeps presenting the raster/cover plate,
        so a partially-resident frame can never surface as a transparent
        preview. The engine view submits this frame's uploads internally
        (``resourceUpdate``) even when it draws nothing, so the next frame
        makes progress while the raster stays up.

        Returns ``True`` only on the covered handover (the caller then skips
        the raster path and ``_settle_present`` fires at most once for the
        transition). ``False`` on any partial miss or error. Never raises.
        """
        try:
            if self._tiled_source is None:
                return False
            renderer = self._ensure_tile_renderer()
            if renderer is None or not renderer.has_source():
                return False
            result = renderer.render(
                command_buffer,
                updates=updates,
                target=target,
                clear_color=clear,
                view=TiledImageView(
                    zoom=float(getattr(self, "_zoom", 1.0) or 1.0),
                    pan=(
                        float(getattr(self, "_pan_x", 0.0) or 0.0),
                        float(getattr(self, "_pan_y", 0.0) or 0.0),
                    ),
                    fb_size=(fb_w, fb_h),
                ),
            )
            covered = bool(getattr(result, "covered", False))
            if covered:
                try:
                    from tabs.image_gallery.debug import ql_cover

                    ql_cover(
                        "tiled handover: covered=True instances=%s resident=%s",
                        getattr(result, "instances", None),
                        getattr(result, "resident", None),
                    )
                except Exception:
                    pass
                self._settle_present()
                return True
            try:
                from tabs.image_gallery.debug import ql_cover

                ql_cover(
                    "tiled partial: covered=False drawn=%s instances=%s "
                    "resident=%s -> raster/cover stays",
                    getattr(result, "drawn", None),
                    getattr(result, "instances", None),
                    getattr(result, "resident", None),
                )
            except Exception:
                pass
            return False
        except Exception:
            logger.debug("QuickLook preview: tiled frame failed open", exc_info=True)
            return False

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self._refresh_plan()
        except Exception:
            pass

    # -- frame raster -----------------------------------------------------------

    def _raster_frame(self, target) -> tuple[int, int, bytes] | None:
        """Frame raster: single ResolvedLayer → cache → zoom/pan crop."""
        try:
            composition = self._active_composition
            layers = getattr(composition, "layers", ()) or ()
            if not layers:
                return None
            source = getattr(layers[0], "image", None)
            if source is None:
                return None
            src_w, src_h = pixel_source_size(source)
            if src_w <= 0 or src_h <= 0:
                return None
            try:
                size = target.pixelSize()
                fb_w, fb_h = max(1, int(size.width())), max(1, int(size.height()))
            except Exception:
                return None
            try:  # last live fb for the lazy need computation (no behavior change).
                self._last_fb = (int(fb_w), int(fb_h))
            except Exception:
                pass
            try:
                generation = int(getattr(source, "generation", 0))
            except Exception:
                generation = 0
            key = (id(source), generation, int(src_w), int(src_h), fb_w, fb_h,
                   round(self._zoom, 4), round(self._pan_x, 4), round(self._pan_y, 4),
                   self._ql_levels_token())
            if key == self._frame_key and self._frame_bytes is not None:
                return self._frame_bytes
            full = self._decoded_image(source, src_w, src_h)
            if full is None or full.isNull():
                return None
            try:
                lod = self._lod_frame(full, fb_w, fb_h)
            except Exception:
                lod = None
            if lod is not None:
                frame = lod
            else:
                try:
                    from tabs.image_gallery.ui.quick_look.preview_zoom import zoomed_frame
                except Exception:
                    return None
                frame = zoomed_frame(full, fb_w, fb_h, self._zoom, self._pan_x, self._pan_y)
            if frame is None:
                return None
            self._frame_key = key
            self._frame_bytes = frame
            return frame
        except Exception:
            logger.debug("QuickLook preview: raster failed open", exc_info=True)
            return None

    def _decoded_image(self, source, src_w: int, src_h: int) -> QImage | None:
        """Host image via the frozen pyramid seam (bounded, no full frame).

        Samples the held (coarse, edge-capped by the host) store verbatim
        through ``PyramidPixelStore.best_pixels`` — ``read_array`` only, so
        no full-frame materialize and no second cache. Miss (stale/unbuilt
        level, unreadable box) fails closed to None; the frame is skipped
        and the QLabel fallback owns the pane.
        """
        try:
            from engine.store.pyramid_pixel_store import PyramidPixelStore
        except Exception:
            return None
        try:
            w, h = int(src_w), int(src_h)
            if w <= 0 or h <= 0:
                return None
            pyramid = PyramidPixelStore(source)
            try:
                image = pyramid.best_pixels((0, 0, w, h), 1.0)
            finally:
                try:
                    pyramid.close()  # derived levels only; base owned by host
                except Exception:
                    pass
        except Exception:
            return None
        if image is None or image.isNull():
            return None
        try:
            # Never hold a 40k host image for a ~640px pane: downscale once.
            edge = max(int(image.width()), int(image.height()))
            if edge > _DECODE_EDGE_CAP and edge > 0:
                small = image.scaled(
                    _DECODE_EDGE_CAP,
                    _DECODE_EDGE_CAP,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if small is not None and not small.isNull():
                    image = small
        except Exception:
            pass
        return image

    def _lod_frame(self, full, fb_w: int, fb_h: int) -> tuple[int, int, bytes] | None:
        """Zoomed frame from the demand pyramid's best level (None = use coarse).

        Same window as ``zoomed_frame`` — pan math comes from the shared
        ``preview_zoom._axis``, so the crop agrees with the coarse path by
        construction — but pixels come from ``PyramidPixelStore.best_pixels``
        (shared ``select_level`` LOD: display-px per full-res px picks the
        level) instead of a CPU-upscaled coarse. Active ONLY past 1.0x with
        a live pyramid; every miss fails closed to None and the caller
        falls back to today's path bit-identically. Never raises.
        """
        try:
            try:
                z = float(getattr(self, "_zoom", 1.0))
            except Exception:
                return None
            if not z > 1.0 + 1e-9:
                return None  # no-zoom path stays bit-identical (coarse only).
            try:
                pyr = getattr(self, "_ql_pyramid", None)
                full_store = getattr(self, "_ql_full_store", None)
                if pyr is None or full_store is None:
                    return None
                if not bool(getattr(pyr, "valid", False)):
                    return None
                if not bool(getattr(full_store, "is_open", False)):
                    return None
            except Exception:
                return None
            try:
                cw, ch = int(full.width()), int(full.height())
                fb_w, fb_h = int(fb_w), int(fb_h)
                if cw <= 0 or ch <= 0 or fb_w <= 0 or fb_h <= 0:
                    return None
                fw, fh = pixel_source_size(full_store)
                fw, fh = int(fw), int(fh)
                if fw <= 0 or fh <= 0:
                    return None
            except Exception:
                return None
            try:  # visible window in coarse-dest px (zoomed_frame geometry).
                scale = min(float(fb_w) / float(cw), float(fb_h) / float(ch)) * z
                if not scale > 0:
                    return None
                dest_w = max(1, int(round(cw * scale)))
                dest_h = max(1, int(round(ch * scale)))
                from tabs.image_gallery.ui.quick_look.preview_zoom import _axis

                try:
                    px, py = float(self._pan_x), float(self._pan_y)
                except Exception:
                    px, py = 0.0, 0.0
                dx, sx, cw2 = _axis(dest_w, fb_w, px)
                dy, sy, ch2 = _axis(dest_h, fb_h, py)
                if cw2 <= 0 or ch2 <= 0:
                    return None
            except Exception:
                return None
            try:  # dest px → coarse px → full-res px (best_pixels clamps too).
                import math

                rx, ry = float(fw) / float(cw), float(fh) / float(ch)
                left = max(0, int(math.floor(sx / scale * rx)))
                top = max(0, int(math.floor(sy / scale * ry)))
                right = min(fw, int(math.ceil((sx + cw2) / scale * rx)))
                bottom = min(fh, int(math.ceil((sy + ch2) / scale * ry)))
                if right <= left or bottom <= top:
                    return None
                dest_scale = min(float(fb_w) / float(fw), float(fb_h) / float(fh)) * z
                img = pyr.best_pixels((left, top, right, bottom), dest_scale)
            except Exception:
                return None
            try:
                _bad = img is None or img.isNull()
            except Exception:
                _bad = True
            if _bad:
                return None
            try:  # blit the level crop onto the fb window (zoomed_frame tail).
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QImage, QPainter

                scaled = img.scaled(
                    int(cw2), int(ch2),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if scaled is None or scaled.isNull():
                    return None
                canvas = QImage(fb_w, fb_h, QImage.Format.Format_RGBA8888_Premultiplied)
                canvas.fill(Qt.GlobalColor.transparent)
                painter = QPainter(canvas)
                try:
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.drawImage(int(dx), int(dy), scaled, 0, 0, int(cw2), int(ch2))
                finally:
                    painter.end()
                premult = canvas.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
                stride = fb_w * 4
                raw = bytes(premult.constBits())
                row_stride = int(premult.bytesPerLine())
                if row_stride == stride:
                    pixels = raw[: stride * fb_h]
                else:
                    pixels = b"".join(
                        raw[y * row_stride: y * row_stride + stride] for y in range(fb_h)
                    )
                if len(pixels) != stride * fb_h:
                    return None
                return (fb_w, fb_h, pixels)
            except Exception:
                return None
        except Exception:
            logger.debug("QuickLook preview: LOD raster failed open", exc_info=True)
            return None

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Wheel = cursor-anchored zoom (MC parity); floor snaps pan to origin."""
        try:
            from tabs.image_gallery.ui.quick_look.preview_zoom import wheel_zoom_pan

            pos = event.position()
            got = wheel_zoom_pan(
                getattr(self, "_zoom", 1.0), getattr(self, "_pan_x", 0.0),
                getattr(self, "_pan_y", 0.0), event.angleDelta().y(),
                float(pos.x()) / max(1, int(self.width())),
                float(pos.y()) / max(1, int(self.height())),
            )
            if got is not None:
                self._zoom, self._pan_x, self._pan_y = got
                self._frame_key = None
                self.update()
            event.accept()
        except Exception:
            pass
        try:  # zoom past 1.0 demands the full pyramid (dwell covers 1.0).
            if float(getattr(self, "_zoom", 1.0)) > 1.0:
                self._maybe_demand_build("zoom")
        except Exception:
            pass

    def mousePressEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import Qt as _Qt

            if event.button() == _Qt.MouseButton.MiddleButton:
                pos = event.position()
                self._drag_last = (float(pos.x()), float(pos.y()))
                self.setCursor(_Qt.CursorShape.ClosedHandCursor)
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        try:
            last = getattr(self, "_drag_last", None)
            if last is not None:
                from tabs.image_gallery.ui.quick_look.preview_zoom import drag_pan

                pos = event.position()
                got = drag_pan(
                    getattr(self, "_pan_x", 0.0), getattr(self, "_pan_y", 0.0),
                    float(pos.x()) - last[0], float(pos.y()) - last[1],
                    max(1, int(self.width())), max(1, int(self.height())),
                    getattr(self, "_zoom", 1.0),
                )
                if got is not None:
                    self._pan_x, self._pan_y = got
                    self._frame_key = None
                    self.update()
                self._drag_last = (float(pos.x()), float(pos.y()))
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtCore import Qt as _Qt

            if event.button() == _Qt.MouseButton.MiddleButton:
                self._drag_last = None
                self.setCursor(_Qt.CursorShape.ArrowCursor)
            super().mouseReleaseEvent(event)
        except Exception:
            pass
