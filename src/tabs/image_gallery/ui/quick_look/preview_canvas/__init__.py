"""Quick Look single-quad GPU preview -- gallery tab, deliberately canvas-light.

``QuickLookCanvasWidget`` is a minimal ``QRhiWidget`` showing one
aspect-fit image quad. It is intentionally far lighter than the compare
tabs: no scene tree, no feature passes, no gestures, no overlays, no
labels.

Seam rules (frozen with host/tests): one quad from _active_composition
via the shared applicator only; pixels from the caller-provided store
sampled verbatim through ``PyramidPixelStore.best_pixels`` (bounded
``read_array`` only -- never ``qimage_from_pixel_source``, never a host
upload cache, never a full-frame materialize); GPU objects belong to
TexturedOverlayShell only. The host hands this widget a bounded coarse
store (``preview_canvas_host._coarse_store_for``); a miss samples to
None and the frame is skipped. Fail open; previewFailed -> QLabel
fallback, firstFramePresented (settled present + restack, MC parity)
-> cover drop.

Demand-built LAZY levels (sharp zoom): the coarse store above still
drives the first frame exactly as before; on zoom>1.0 or dwell
(``note_ql_source`` arms the dwell timer -- never on plain walks) only
the levels needed for the CURRENT zoom are built (``best_level_for_scale``
target, ``build_next_level`` until it lands or the walk aborts it)
through the shared ``engine.pyramid.coordinator.PyramidBuildCoordinator`` (no
second builder, GIMP-style: built levels stay, deeper zooms add more).
The zoomed frame then samples the best BUILT level through
``PyramidPixelStore.best_pixels`` (shared ``select_level`` LOD) instead
of CPU-upscaling the coarse; unbuilt levels hold the coarse frame until
they land (``best_pixels`` fails closed to None).

Module -> package (plan-gallery-split-2026-10-17, Part C2): this was
``preview_canvas.py``; the ``QuickLookCanvasWidget`` lifecycle bodies moved
verbatim into six per-phase modules -- method/function names and signatures
unchanged -- and the class keeps same-named thin delegators here:

- ``source``: source lifetime (held-store ownership + watchdog) and the
  module decode/shader helpers.
- ``tiled_source``: the additive tiled single-source path.
- ``lazy_levels``: demand-built lazy levels (sharp zoom).
- ``applicator``: the shared-applicator plan.
- ``rhi_entry``: QRhiWidget entry points (frame sequencing).
- ``batches``: resource-update-batch take/consume/drain + the outstanding
  counter (the batch-ownership invariant).
- ``raster``: the frame raster + wheel/mouse interaction.

Every module-level name the old single file exposed is re-exported here, so
``...quick_look.preview_canvas`` keeps its full surface for importers/tests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QRhiDepthStencilClearValue
from PySide6.QtWidgets import QRhiWidget, QSizePolicy

from engine.frame.present import begin_source, note_presented
from engine.gpu.tiled_image_view import (
    LodPolicy,
    SingleImageTiledView,
    TiledImageSource,
    TiledImageView,
    TiledViewHooks,
    contain_fit_scale,
    load_tiled_image_shader,
)
from engine.overlay import TexturedOverlayBinding, TexturedOverlayShell
from engine.store.tiled_pixel_store import pixel_source_size
from ui.canvas_infra.rhi.rhi_backend import configure_rhi_widget
from ui.canvas_presentation.composition import LayerNode
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan
from tabs.image_gallery.ui.quick_look.preview_canvas_host import settle_first_frame
from tabs.image_gallery.ui.quick_look.preview_zoom import ViewportState
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

# No-present watchdog: a canvas that shows no frame within this window is
# presumed broken (dead RHI, missing shaders) and must yield to QLabel --
# a transparent widget shows the windows behind it as "garbage".
_NO_FRAME_TIMEOUT_MS = 1500

# Decode caps owned by services/decode_policy.py (single home); the
# _DECODE_EDGE_CAP / _QL_FULL_EDGE_CAP aliases below keep historic names.
from tabs.image_gallery.services.decode_policy import (
    PREVIEW_FULL_DECODE_EDGE as _DECODE_EDGE_CAP,
    QL_FULL_EDGE_CAP as _QL_FULL_EDGE_CAP,
    exceeds_edge,
)

# Phase modules (thin-owner delegator targets); imported here so the class
# delegators stay one-liners and their names are part of this package surface.
from . import applicator as _applicator
from . import lazy_levels as _lazy_levels
from . import raster as _raster
from . import rhi_entry as _rhi_entry
from . import source as _source
from . import tiled_source as _tiled_source

# Re-export the module-level names the old single file exposed.
_ql_decode_full_store = _source._ql_decode_full_store
_overlay_shader_dir = _source._overlay_shader_dir
_IDENTITY_CLIP = _rhi_entry._IDENTITY_CLIP
_CLEAR_OPAQUE = _rhi_entry._CLEAR_OPAQUE
_QL_DWELL_MS = _lazy_levels._QL_DWELL_MS


class QuickLookCanvasWidget(QRhiWidget):
    """Minimal single-quad GPU preview (set_source/clear_source + repaint)."""

    previewFailed = Signal()
    firstFramePresented = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # One viewport state, shared on request with a second view (the
        # source inset canvas) via ``bind_view``. ``_zoom/_pan_x/_pan_y``
        # below are properties over this object, so every existing read
        # (raster fit/crop, lazy levels, region mapping) sees the shared
        # view without a parallel variable.
        self._viewport = ViewportState()
        self._viewport.subscribe(self._on_viewport_changed)
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
        self._ql_tiled_pending = None
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
        self._tile_bound_source = None
        self._tile_level_ready = False
        self._ql_demand_svc = None
        try:
            self._present_debt = begin_source(None)
        except Exception:
            self._present_debt = None
        try:
            configure_rhi_widget(self)
        except Exception:
            logger.debug("QuickLook preview: RHI setup failed; staying inert", exc_info=True)

    # -- source (moved to preview_canvas.source) -----------------------------

    def set_source(self, store, *, preserve_view: bool = False) -> None:
        """Thin delegator to ``preview_canvas.source.set_source``."""
        return _source.set_source(self, store, preserve_view=preserve_view)

    def _arm_watchdog(self, gen=None) -> None:
        """Thin delegator to ``preview_canvas.source._arm_watchdog``."""
        return _source._arm_watchdog(self, gen)

    def _on_watchdog(self, expected_gen=None) -> None:
        """Thin delegator to ``preview_canvas.source._on_watchdog``."""
        return _source._on_watchdog(self, expected_gen)

    def clear_source(self) -> None:
        """Thin delegator to ``preview_canvas.source.clear_source``."""
        return _source.clear_source(self)

    def _close_held_store(self) -> None:
        """Thin delegator to ``preview_canvas.source._close_held_store``."""
        return _source._close_held_store(self)

    # -- view ----------------------------------------------------------------

    @property
    def _zoom(self) -> float:
        """Zoom of the (possibly shared) viewport — never a parallel copy."""
        return self._viewport.zoom

    @_zoom.setter
    def _zoom(self, value) -> None:
        self._viewport.zoom = value

    @property
    def _pan_x(self) -> float:
        return self._viewport.pan_x

    @_pan_x.setter
    def _pan_x(self, value) -> None:
        self._viewport.pan_x = value

    @property
    def _pan_y(self) -> float:
        return self._viewport.pan_y

    @_pan_y.setter
    def _pan_y(self, value) -> None:
        self._viewport.pan_y = value

    def _on_viewport_changed(self) -> None:
        """Repaint this view after any bound surface moved the viewport."""
        try:
            self._frame_key = None
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def set_view(self, zoom, pan_x, pan_y) -> None:
        """Assign the viewport; every view bound to it follows (never raises)."""
        try:
            self._viewport.set_view(zoom, pan_x, pan_y)
        except Exception:
            pass

    def bind_view(self, other) -> None:
        """Share *other*'s viewport: one state, N views (idempotent).

        The main preview owns the viewport; the source inset binds to it so
        a wheel/drag on either surface moves both (plan-gallery-ql-source-canvas).
        Foreign doubles without a ``_viewport`` are ignored (fail-open).
        """
        try:
            shared = other._viewport
        except Exception:
            return
        if shared is None or shared is self._viewport:
            return
        try:
            self._viewport.unsubscribe(self._on_viewport_changed)
        except Exception:
            pass
        self._viewport = shared
        try:
            shared.subscribe(self._on_viewport_changed)
        except Exception:
            pass
        self._on_viewport_changed()

    def current_view(self) -> tuple[float, float, float]:
        """Live view as ``(zoom, pan_x, pan_y)`` — total, never raises.

        The declared read side of the view: the host's static cover plate is
        built through ``preview_canvas_host._cover_pixmap_from_full`` from
        THIS accessor, so a within-series walk (which preserves the view)
        never flashes a fit-frame plate before the preserved frame lands.
        Degenerate/absent stored values fail open to ``(1.0, 0.0, 0.0)``.
        """
        try:
            return (float(self._zoom), float(self._pan_x), float(self._pan_y))
        except Exception:
            return (1.0, 0.0, 0.0)

    # -- tiled_source (moved to preview_canvas.tiled_source) -----------------

    def set_tiled_source(self, key, store, *, preserve_view: bool = False) -> None:
        """Thin delegator to ``preview_canvas.tiled_source.set_tiled_source``."""
        return _tiled_source.set_tiled_source(self, key, store, preserve_view=preserve_view)

    def clear_tiled_source(self) -> None:
        """Thin delegator to ``preview_canvas.tiled_source.clear_tiled_source``."""
        return _tiled_source.clear_tiled_source(self)

    def _sampler_for_tiles(self, name):
        """Thin delegator to ``preview_canvas.tiled_source._sampler_for_tiles``."""
        return _tiled_source._sampler_for_tiles(self, name)

    def _ensure_tile_renderer(self):
        """Thin delegator to ``preview_canvas.tiled_source._ensure_tile_renderer``."""
        return _tiled_source._ensure_tile_renderer(self)

    def _ql_bound_levels(self, key) -> tuple:
        """Thin delegator to ``preview_canvas.tiled_source._ql_bound_levels``."""
        return _tiled_source._ql_bound_levels(self, key)

    def _destroy_tile_renderer(self) -> None:
        """Thin delegator to ``preview_canvas.tiled_source._destroy_tile_renderer``."""
        return _tiled_source._destroy_tile_renderer(self)

    # -- lazy_levels (moved to preview_canvas.lazy_levels) -------------------

    def note_ql_source(self, path) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels.note_ql_source``."""
        return _lazy_levels.note_ql_source(self, path)

    def _ql_on_dwell(self, gen) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_on_dwell``."""
        return _lazy_levels._ql_on_dwell(self, gen)

    def _fire_ql_tiled_pending(self, store=None) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._fire_ql_tiled_pending``."""
        return _lazy_levels._fire_ql_tiled_pending(self, store)

    def _drop_ql_demand(self) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._drop_ql_demand``."""
        return _lazy_levels._drop_ql_demand(self)

    def _ql_coordinator_lazy(self):
        """Thin delegator to ``preview_canvas.lazy_levels._ql_coordinator_lazy``."""
        return _lazy_levels._ql_coordinator_lazy(self)

    def _ql_demand_service_lazy(self):
        """Thin delegator to ``preview_canvas.lazy_levels._ql_demand_service_lazy``."""
        return _lazy_levels._ql_demand_service_lazy(self)

    def _ql_abort_fn(self, full, gen):
        """Thin delegator to ``preview_canvas.lazy_levels._ql_abort_fn``."""
        return _lazy_levels._ql_abort_fn(self, full, gen)

    def _ql_fb_estimate(self) -> tuple[int, int]:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_fb_estimate``."""
        return _lazy_levels._ql_fb_estimate(self)

    def _ql_needed_level(self, fb_w: int, fb_h: int, full_w: int, full_h: int, zoom) -> int:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_needed_level``."""
        return _lazy_levels._ql_needed_level(self, fb_w, fb_h, full_w, full_h, zoom)

    def _ql_resume_build(self, full, gen) -> bool:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_resume_build``."""
        return _lazy_levels._ql_resume_build(self, full, gen)

    def _maybe_demand_build(self, reason: str = "") -> bool:
        """Thin delegator to ``preview_canvas.lazy_levels._maybe_demand_build``."""
        return _lazy_levels._maybe_demand_build(self, reason)

    def _on_ql_full_ready(self, store, gen) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._on_ql_full_ready``."""
        return _lazy_levels._on_ql_full_ready(self, store, gen)

    def _on_ql_decode_finished(self, gen) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._on_ql_decode_finished``."""
        return _lazy_levels._on_ql_decode_finished(self, gen)

    def _ql_on_level(self, payload) -> None:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_on_level``."""
        return _lazy_levels._ql_on_level(self, payload)

    def _ql_levels_token(self) -> int:
        """Thin delegator to ``preview_canvas.lazy_levels._ql_levels_token``."""
        return _lazy_levels._ql_levels_token(self)

    # -- applicator (moved to preview_canvas.applicator) ---------------------

    def _refresh_plan(self) -> None:
        """Thin delegator to ``preview_canvas.applicator._refresh_plan``."""
        return _applicator._refresh_plan(self)

    # -- rhi_entry (moved to preview_canvas.rhi_entry) -----------------------

    def _skip_frame(self, reason: str) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._skip_frame``."""
        return _rhi_entry._skip_frame(self, reason)

    def initialize(self, command_buffer) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.rhi_entry.initialize``."""
        return _rhi_entry.initialize(self, command_buffer)

    def releaseResources(self) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.rhi_entry.releaseResources``."""
        return _rhi_entry.releaseResources(self)

    def _pump_next_frame(self) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._pump_next_frame``."""
        return _rhi_entry._pump_next_frame(self)

    def _pump_throttled(self, stall_frames: int) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._pump_throttled``."""
        return _rhi_entry._pump_throttled(self, stall_frames)

    def _fire_throttled_pump(self) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._fire_throttled_pump``."""
        return _rhi_entry._fire_throttled_pump(self)

    def _reset_tiled_pump_state(self) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._reset_tiled_pump_state``."""
        return _rhi_entry._reset_tiled_pump_state(self)

    def render(self, command_buffer) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.rhi_entry.render``."""
        return _rhi_entry.render(self, command_buffer)

    def _settle_present(self) -> None:
        """Thin delegator to ``preview_canvas.rhi_entry._settle_present``."""
        return _rhi_entry._settle_present(self)

    def _render_tiled(self, command_buffer, updates, target, clear, fb_w, fb_h) -> bool:
        """Thin delegator to ``preview_canvas.rhi_entry._render_tiled``."""
        return _rhi_entry._render_tiled(self, command_buffer, updates, target, clear, fb_w, fb_h)

    def _ql_view_hooks(self) -> TiledViewHooks:
        """Thin delegator to ``preview_canvas.rhi_entry._ql_view_hooks``."""
        return _rhi_entry._ql_view_hooks(self)

    def _tiled_level_ready(self) -> bool:
        """Thin delegator to ``preview_canvas.rhi_entry._tiled_level_ready``."""
        return _rhi_entry._tiled_level_ready(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.rhi_entry.resizeEvent``."""
        return _rhi_entry.resizeEvent(self, event)

    # -- raster (moved to preview_canvas.raster) -----------------------------

    def _raster_frame(self, target) -> tuple[int, int, bytes] | None:
        """Thin delegator to ``preview_canvas.raster._raster_frame``."""
        return _raster._raster_frame(self, target)

    def _compute_raster_frame(self, target) -> tuple[int, int, bytes] | None:
        """Thin delegator to ``preview_canvas.raster._compute_raster_frame``."""
        return _raster._compute_raster_frame(self, target)

    def _decoded_image(self, source, src_w: int, src_h: int) -> QImage | None:
        """Thin delegator to ``preview_canvas.raster._decoded_image``."""
        return _raster._decoded_image(self, source, src_w, src_h)

    def _lod_frame(self, full, fb_w: int, fb_h: int) -> tuple[int, int, bytes] | None:
        """Thin delegator to ``preview_canvas.raster._lod_frame``."""
        return _raster._lod_frame(self, full, fb_w, fb_h)

    def wheelEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.raster.wheelEvent``."""
        return _raster.wheelEvent(self, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.raster.mousePressEvent``."""
        return _raster.mousePressEvent(self, event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.raster.mouseMoveEvent``."""
        return _raster.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """Thin delegator to ``preview_canvas.raster.mouseReleaseEvent``."""
        return _raster.mouseReleaseEvent(self, event)
