"""Quick-look canvas: QRhiWidget entry points (frame sequencing).

Audit-Meta: pattern=thin-owner reason="one QRhiWidget frame-sequencing lifecycle split from preview_canvas.py (rhi_entry/raster/source); the resource-update-batch take/consume/drain invariant and its counter moved to batches.py (task-gallery-ql-preview-batch-module-2026-10-17)"

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).

Owns ``initialize``/``releaseResources``/``render`` + the present pump and
the tiled/raster handover decision for one frame. Batch ownership (take /
consume / drain + the outstanding counter) lives in ``batches``.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor

from engine.frame.present import begin_source, note_presented
from engine.gpu.mip_cascade import MipCascadeNotReady
from engine.gpu.rt_y_orientation import composited_clip_correction
from engine.gpu.tiled_image_view import (
    LodPolicy,
    TiledImageView,
    TiledViewHooks,
    contain_fit_scale,
)
from engine.overlay import TexturedOverlayBinding
from tabs.image_gallery.ui.quick_look.preview_canvas_host import settle_first_frame
from core.log_names import APP_LOGGER_NAME

from . import batches as _batches
from .source import _overlay_shader_dir

logger = logging.getLogger(APP_LOGGER_NAME)

_CLEAR_OPAQUE = QColor(0, 0, 0, 255)


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


def _retry_tiled_frame(self) -> None:
    """Backed-off retry after a failed tiled attempt. Never raises.

    A raised attempt used to wait for an unrelated repaint (mouse move,
    the next walk): live 2026-10-17 a series step failed its first two
    tiled frames and then sat on the raster plate until the next click,
    because nothing asked for frame three. Requesting one more frame here
    lets the retry the cascade needs actually arrive.

    Throttled, never full rate: a failure that keeps repeating must not
    spin ``update()`` at GUI-loop rate (the same discipline as the
    plateau backoff in the hold path below).
    """
    try:
        stall = int(getattr(self, "_tiled_stall_frames", 0) or 0) + 1
        self._tiled_stall_frames = stall
        self._pump_throttled(stall)
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
        tiled_updates, _ = _batches.take(self, rhi)
        if tiled_updates is not None and self._render_tiled(
            command_buffer, tiled_updates, target, clear, fb_w, fb_h
        ):
            return
        # Raster path only. INVARIANT: every batch taken from
        # ``nextResourceUpdateBatch()`` is consumed on every path out of
        # render() -- see ``preview_canvas.batches`` (the early returns below
        # therefore drain).
        updates, ok = _batches.take(self, rhi)
        if not ok:
            return self._skip_frame("no-batch")
        try:
            self._shell.stage_quad(updates)
            # Where raster row 0 lands is a backend convention, never a local
            # answer: the shell quad carries row 0 (`v == 0`) at clip y=+1, so
            # identity is only right on a y-up NDC backend and mirrors the
            # preview on Vulkan/Metal. Same COMPOSITED case the tiled path
            # (engine.gpu.tiled_image_view) and engine/overlay/shell.py's
            # `clip_matrix()` use -- one source of truth, no local literal.
            self._shell.stage_clip(updates, composited_clip_correction(rhi))
        except Exception:
            _batches.drain(self, command_buffer, updates)
            return self._skip_frame("stage-failed")
        frame = self._raster_frame(target)
        if frame is None:
            self._skip_frame("raster-no-frame")
        try:
            self._shell.upload_frame(updates, target, frame)
        except Exception:
            _batches.drain(self, command_buffer, updates)
            return self._skip_frame("upload-failed")
        if not _batches.begin_pass(self, command_buffer, target, clear, updates):
            _batches.drain(self, command_buffer, updates)
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
    it; on the guards above (no source / no renderer) it is drained here so
    no path abandons a batch (see ``preview_canvas.batches``).

    Returns ``True`` only on the covered handover (the caller then skips
    the raster path and ``_settle_present`` fires at most once for the
    transition). ``False`` on any partial miss or error. Never raises.
    """
    handed = False
    try:
        if self._tiled_source is None:
            _batches.drain(self, command_buffer, updates)
            return False
        renderer = self._ensure_tile_renderer()
        if renderer is None or not renderer.has_source():
            _batches.drain(self, command_buffer, updates)
            return False
        # Past this point the engine view owns the batch: ``render`` submits
        # it internally (``command_buffer.resourceUpdate``), so the caller
        # must not drain it again.
        handed = True
        _batches.transfer(self, updates)
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
    except MipCascadeNotReady as exc:
        # "Not ready yet", not a broken frame: the mip cascade could not
        # build its probe target on this attempt (transient right after a
        # store swap -- see engine.gpu.mip_cascade). The raster plate stays
        # up; the fact goes to the cover timeline instead of a traceback,
        # and the backed-off retry below is what makes the takeover land.
        if not handed:
            _batches.drain(self, command_buffer, updates)
        try:
            from tabs.image_gallery.debug import ql_cover

            ql_cover("tiled not ready: %s", exc)
        except Exception:
            pass
        _retry_tiled_frame(self)
        return False
    except Exception:
        if not handed:
            _batches.drain(self, command_buffer, updates)
        logger.debug("QuickLook preview: tiled frame failed open", exc_info=True)
        _retry_tiled_frame(self)
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
