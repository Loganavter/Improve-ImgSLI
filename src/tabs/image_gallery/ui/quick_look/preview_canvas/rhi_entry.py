"""Quick-look canvas: QRhiWidget entry points (frame sequencing).

Audit-Meta: pattern=thin-owner size=exempt reason="one QRhiWidget frame-sequencing lifecycle split from preview_canvas.py (rhi_entry/raster/source); the batch take/consume/drain invariant is one concern and splitting it would scatter ownership across files"

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).

Owns ``initialize``/``releaseResources``/``render`` + the present pump and
the tiled/raster handover decision for one frame.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QRhiDepthStencilClearValue

from engine.frame.present import begin_source, note_presented
from engine.gpu.tiled_image_view import (
    LodPolicy,
    TiledImageView,
    TiledViewHooks,
    contain_fit_scale,
)
from engine.overlay import TexturedOverlayBinding
from tabs.image_gallery.ui.quick_look.preview_canvas_host import settle_first_frame

from .source import _overlay_shader_dir

logger = logging.getLogger("ImproveImgSLI")

# Identity clip matrix for the fullscreen shell quad (the preview has no
# viewport transform -- aspect-fit is baked into the uploaded raster).
_IDENTITY_CLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)

_CLEAR_OPAQUE = QColor(0, 0, 0, 255)


# -- QRhiWidget entry points ------------------------------------------------


def _skip_frame(self, reason: str) -> None:
    """Log a skipped frame at DEBUG (diagnostic-only, never raises)."""
    try:
        logger.debug("QuickLook preview: skip frame (%s)", reason)
    except Exception:
        pass


def _note_rhi_batch(self, delta: int) -> int:
    """Advance the outstanding-batch counter (taken minus consumed).

    Diagnostic-only: the counter is a plain int on the widget
    (``_ql_rhi_batches_outstanding``) and the line is emitted through
    ``ql_cover`` only under the existing ``IMGSLI_QL_COVER_DEBUG`` gate
    (DEBUGGING.md rule 5 -- own flag, silent by default), so this is
    fail-open and effectively free when the gate is off. Never raises.
    """
    try:
        outstanding = int(getattr(self, "_ql_rhi_batches_outstanding", 0) or 0) + int(delta)
    except Exception:
        return 0
    try:
        self._ql_rhi_batches_outstanding = outstanding
    except Exception:
        pass
    try:
        from tabs.image_gallery.debug import ql_cover, ql_cover_enabled

        if ql_cover_enabled():
            ql_cover(
                "QuickLook preview: rhi batches outstanding=%s (delta=%+d)",
                outstanding,
                int(delta),
            )
    except Exception:
        pass
    return outstanding


def _drain_batch(self, command_buffer, batch) -> None:
    """Consume a taken-but-unused batch via ``command_buffer.resourceUpdate``.

    The tree-wide idiom for a batch that no draw steals (see
    ``engine.gpu.tiled_image_view.render``): submitting it returns the
    batch to QRhi's shared resource-update pool. Skipping this on an early
    ``return`` abandons the batch -- it is never recycled, the pool is
    exhausted after 64 frames and Qt's own widget-compositing flush later
    replays a stale batch whose recorded uploads reference resources
    destroyed in the meantime (SIGSEGV photographed in
    ``QWidgetRepaintManager::flush -> rhiFlush``). Never raises.
    """
    if batch is None:
        return
    try:
        command_buffer.resourceUpdate(batch)
    except Exception:
        pass
    _note_rhi_batch(self, -1)


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
    # Per-pump logging is cover-timeline only (IMGSLI_QL_COVER_DEBUG):
    # at full streaming rate this fires hundreds of times per second.
    try:
        from tabs.image_gallery.debug import ql_cover as _ql_log

        _ql_log("QuickLook preview: pump posted=%s", bool(_posted))
    except Exception:
        pass
    if not _posted:
        try:
            self.update()
        except Exception:
            pass


def _pump_throttled(self, stall_frames: int) -> None:
    """Backoff pump for a stalled (no-progress) tile stream.

    Same destination as ``_pump_next_frame`` but rate-limited: when
    residency plateaus without reaching ``covered`` (missing level,
    unsettled cascade), full-rate pumping saturates the GUI loop and
    the log for zero forward progress. One pending singleShot at a
    time, 32ms → 250ms cap, so uploads still drain to completion.
    Never raises.
    """
    try:
        if bool(getattr(self, "_throttled_pump_pending", False)):
            return
        self._throttled_pump_pending = True
    except Exception:
        return
    try:
        shift = max(0, min(int(stall_frames), 4))
        interval = min(250, 16 * (2 ** int(shift)))
    except Exception:
        interval = 64
    try:
        from PySide6.QtCore import QTimer as _QTimer

        _QTimer.singleShot(int(interval), self._fire_throttled_pump)
    except Exception:
        try:
            self._throttled_pump_pending = False
        except Exception:
            pass


def _fire_throttled_pump(self) -> None:
    """Fire one throttled pump (singleShot callback). Never raises."""
    try:
        self._throttled_pump_pending = False
    except Exception:
        pass
    try:
        if not bool(self.isVisible()):
            return
    except Exception:
        return
    try:
        self._pump_next_frame()
    except Exception:
        pass


def _reset_tiled_pump_state(self) -> None:
    """Clear pump progress marks (source bind/drop/teardown). Never raises."""
    for attr, val in (
        ("_tiled_pump_mark", None),
        ("_tiled_stall_frames", 0),
        ("_throttled_pump_pending", False),
    ):
        try:
            setattr(self, attr, val)
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
        if tiled_updates is not None:
            _note_rhi_batch(self, 1)
        if tiled_updates is not None and self._render_tiled(
            command_buffer, tiled_updates, target, clear, fb_w, fb_h
        ):
            return
        # Raster path only. INVARIANT: every batch taken from
        # ``nextResourceUpdateBatch()`` is consumed on every path out of
        # render() -- either handed to ``beginPass(...)`` or drained with
        # ``resourceUpdate(batch)`` (also for the tiled batch, on the
        # guards inside ``_render_tiled``). A batch handed out but never
        # submitted is never recycled; after 64 frames QRhi's pool is
        # exhausted and Qt's compositor later flushes a stale batch whose
        # uploads reference destroyed resources (SIGSEGV in
        # QWidgetRepaintManager::flush). Each early return below therefore
        # drains its batch.
        try:
            updates = rhi.nextResourceUpdateBatch()
        except Exception:
            return self._skip_frame("no-batch")
        if updates is not None:
            _note_rhi_batch(self, 1)
        try:
            self._shell.stage_quad(updates)
            self._shell.stage_clip(updates, _IDENTITY_CLIP)
        except Exception:
            _drain_batch(self, command_buffer, updates)
            return self._skip_frame("stage-failed")
        frame = self._raster_frame(target)
        if frame is None:
            self._skip_frame("raster-no-frame")
        try:
            self._shell.upload_frame(updates, target, frame)
        except Exception:
            _drain_batch(self, command_buffer, updates)
            return self._skip_frame("upload-failed")
        try:
            command_buffer.beginPass(
                target,
                clear,
                QRhiDepthStencilClearValue(1.0, 0),
                updates,
            )
        except Exception:
            _drain_batch(self, command_buffer, updates)
            return self._skip_frame("begin-failed")
        # beginPass owns the batch from here (it is submitted, not abandoned).
        _note_rhi_batch(self, -1)
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
    resident) AND a genuine multi-level binding (``_tiled_level_ready``):
    while the tile set is still streaming the caller keeps presenting the
    raster/cover plate, so a partially-resident frame can never surface as
    a transparent preview. The engine view owns the LOD choice + the
    no-seam hold (``LodPolicy(mode="settle")``): ``covered`` is false until
    the zoom-matched target level is resident and its mip cascade drained,
    so a single-level full-res draw shown downscaled never takes over. The
    engine view submits this frame's uploads internally (``resourceUpdate``)
    even when it draws nothing, so the next frame makes progress while the
    raster stays up.

    Batch ownership: the caller hands the frame's batch in ``updates``.
    Once ``renderer.render`` is reached the engine view owns (and submits)
    it; on the guards above (no source / no renderer) it is drained here
    via ``command_buffer.resourceUpdate`` so no path abandons a batch
    (an abandoned batch is never recycled by QRhi's 64-batch pool -> the
    stale-upload SIGSEGV in ``QWidgetRepaintManager::flush``).

    Returns ``True`` only on the covered handover (the caller then skips
    the raster path and ``_settle_present`` fires at most once for the
    transition). ``False`` on any partial miss or error. Never raises.
    """
    handed = False
    try:
        if self._tiled_source is None:
            _drain_batch(self, command_buffer, updates)
            return False
        renderer = self._ensure_tile_renderer()
        if renderer is None or not renderer.has_source():
            _drain_batch(self, command_buffer, updates)
            return False
        # Past this point the engine view owns the batch: ``render`` submits
        # it internally (``command_buffer.resourceUpdate``), so the caller
        # must not drain it again.
        handed = True
        if updates is not None:
            _note_rhi_batch(self, -1)
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
            hooks=self._ql_view_hooks(),
        )
        covered = bool(getattr(result, "covered", False))
        if covered and self._tiled_level_ready():
            try:
                from tabs.image_gallery.debug import ql_cover

                _sw, _sh = renderer.store_size()
                _fit = contain_fit_scale((_sw, _sh), int(fb_w), int(fb_h))
                _z = float(getattr(self, "_zoom", 1.0) or 1.0)
                _px = float(getattr(self, "_pan_x", 0.0) or 0.0)
                _py = float(getattr(self, "_pan_y", 0.0) or 0.0)
                ql_cover(
                    "tiled handover: covered=True instances=%s resident=%s "
                    "store=%sx%s fb=%sx%s fit=(%.4f,%.4f) zoom=%.4f "
                    "pan=(%.4f,%.4f)",
                    getattr(result, "instances", None),
                    getattr(result, "resident", None),
                    _sw, _sh, int(fb_w), int(fb_h),
                    _fit[0], _fit[1], _z, _px, _py,
                )
            except Exception:
                pass
            self._settle_present()
            return True
        try:
            from tabs.image_gallery.debug import ql_cover

            ql_cover(
                "tiled holding: covered=%s level_ready=%s drawn=%s "
                "instances=%s resident=%s -> raster/cover stays",
                covered,
                self._tiled_level_ready(),
                getattr(result, "drawn", None),
                getattr(result, "instances", None),
                getattr(result, "resident", None),
            )
        except Exception:
            pass
        # Keep the residency stream moving: the tiled plan is not yet
        # ``covered``, so it will only complete if frames keep coming.
        # Without this, uploads stall until an unrelated repaint (mouse
        # move) and the coarse raster lingers — or, if the raster also
        # misses, the canvas stays a hole. Pump at full rate ONLY on
        # forward progress (resident count grew): a plateau (same tiles
        # redrawn, coverage never completing) used to spin _pump at full
        # GUI-loop rate forever — log spam plus an event loop too
        # saturated for resize drags. Plateaus back off instead.
        try:
            res_n = int(getattr(result, "resident", 0) or 0)
        except Exception:
            res_n = 0
        drew = bool(getattr(result, "drawn", False))
        if not drew and res_n <= 0:
            return False
        try:
            last_mark = getattr(self, "_tiled_pump_mark", None)
        except Exception:
            last_mark = None
        if last_mark is None or int(res_n) != int(last_mark):
            try:
                self._tiled_pump_mark = int(res_n)
            except Exception:
                pass
            try:
                self._tiled_stall_frames = 0
            except Exception:
                pass
            self._pump_next_frame()
        else:
            try:
                stall = int(getattr(self, "_tiled_stall_frames", 0) or 0) + 1
                self._tiled_stall_frames = stall
            except Exception:
                stall = 1
            self._pump_throttled(stall)
        return False
    except Exception:
        if not handed:
            _drain_batch(self, command_buffer, updates)
        logger.debug("QuickLook preview: tiled frame failed open", exc_info=True)
        return False


def _ql_view_hooks(self) -> TiledViewHooks:
    """Per-frame view hooks: the LOD policy for the bound source.

    QL's demand policy sets ``settle=True``, so the engine view holds the
    prior level until the zoom-matched target is resident + cascade
    drained (the seam-hold QL used to fake by re-binding a level store).
    Read-only (may run on the render thread): uses the service created on
    the GUI thread; no service -> immediate (single-level path ignores the
    policy anyway). Never raises.
    """
    try:
        svc = getattr(self, "_ql_demand_svc", None)
        settle = bool(getattr(getattr(svc, "policy", None), "settle", False))
    except Exception:
        settle = False
    try:
        return TiledViewHooks(
            lods=LodPolicy(mode="settle" if settle else "immediate")
        )
    except Exception:
        return TiledViewHooks()


def _tiled_level_ready(self) -> bool:
    """True only when the tiled view holds a genuine multi-level source.

    A single-level binding (no pyramid, or only level 0 built) is drawn by
    the view's E1 path whose ``covered`` can be true while the full-res
    store is shown downscaled -- per-tile mip edges seam. With >= 2
    registered levels the view's LOD picks a level whose texels are <= 1
    screen px and its ``covered`` is seam-safe, so takeover is allowed.
    Set on rebind (``_ensure_tile_renderer``); never raises.
    """
    try:
        return bool(getattr(self, "_tile_level_ready", False))
    except Exception:
        return False


def resizeEvent(self, event) -> None:  # noqa: N802
    try:
        super(type(self), self).resizeEvent(event)
    except Exception:
        pass
    try:
        self._refresh_plan()
    except Exception:
        pass
