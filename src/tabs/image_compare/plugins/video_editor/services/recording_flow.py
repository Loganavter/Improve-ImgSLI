from __future__ import annotations

import logging
import threading

from core.events import CoreErrorOccurredEvent
from sli_ui_toolkit.workers import GenericWorker
from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def _video_debug(msg: str, *args, **kwargs) -> None:
    # Per-zone gated: only IMGSLI_VIDEO_EDITOR_DEBUG / IMGSLI_IC_VIDEO_DEBUG, not default --debug
    # Always log via Tracer if enabled (IMGSLI_TRACE=1 / --debug) for causal chain
    try:
        from core.tracing.tracer import Tracer

        if Tracer.enabled():
            Tracer.instance().record("video.editor.debug", msg % args if args else msg, kwargs)
    except Exception:
        pass
    if _env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or _env_flag("IMGSLI_IC_VIDEO_DEBUG"):
        logger.warning("[video-editor-debug] " + msg, *args, **kwargs)
    else:
        logger.debug("[video-editor-debug] " + msg, *args, **kwargs)


def _video_enabled() -> bool:
    return _env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or _env_flag("IMGSLI_IC_VIDEO_DEBUG")


class RecordingFlow:
    def __init__(self, controller):
        self.controller = controller
        # Single guard path (ve-p3, X6): every _toggle/_finalize flag
        # transition goes through the helpers below under one lock, so the
        # check-then-set in toggle/finalize is atomic. Flag STORAGE stays on
        # the host controller (plugins/export/controller.py owns it — out of
        # scope); semantics are unchanged, only the access path is unified.
        self._guard_lock = threading.Lock()

    def _begin_toggle(self) -> bool:
        """Atomic check-then-set of the toggle guard. False = busy, reject."""
        with self._guard_lock:
            if (
                self.controller._toggle_recording_in_progress
                or self.controller._recording_finalize_in_progress
            ):
                return False
            self.controller._toggle_recording_in_progress = True
            return True

    def _release_toggle(self) -> None:
        with self._guard_lock:
            self.controller._toggle_recording_in_progress = False

    def _release_toggle_unless_finalizing(self) -> None:
        # Toggle stays held while a finalize worker is in flight; the
        # finalize-finished handler releases it (same as before).
        with self._guard_lock:
            if not self.controller._recording_finalize_in_progress:
                self.controller._toggle_recording_in_progress = False

    def _begin_finalize(self) -> bool:
        """Atomic check-then-set of the finalize guard. False = busy, skip."""
        with self._guard_lock:
            if self.controller._recording_finalize_in_progress:
                return False
            self.controller._recording_finalize_in_progress = True
            return True

    def _finish_finalize(self) -> None:
        with self._guard_lock:
            self.controller._recording_finalize_in_progress = False
            self.controller._toggle_recording_in_progress = False

    def toggle_recording(self, checked: bool | None = None):
        del checked
        controller = self.controller
        _video_debug("toggle_recording called has_data=%s is_recording=%s finalize=%s recorder=%s store=%s", controller.recorder.has_recording_data() if controller.recorder else None, getattr(controller.recorder, "is_recording", None), controller._recording_finalize_in_progress, controller.recorder, getattr(controller.recorder, "store", None) if controller.recorder else None)
        if not self._begin_toggle():
            _video_debug("toggle_recording REJECT in_progress toggle=%s finalize=%s", controller._toggle_recording_in_progress, controller._recording_finalize_in_progress)
            return

        try:
            if controller.recorder.is_recording:
                _video_debug("toggle_recording STOP is_recording True -> stop finalize=False")
                controller.recorder.stop(finalize=False)
                self._sync_controls(
                    is_recording=False,
                    is_paused=False,
                    pause_enabled=False,
                )
                self._finalize_recording_async()
            else:
                _video_debug("toggle_recording START is_recording False -> start")
                controller.recorder.start()
                self._sync_controls(
                    is_recording=True,
                    is_paused=False,
                    pause_enabled=True,
                )
                _video_debug("toggle_recording START done timeline_len=%s", len(getattr(getattr(controller.recorder, "_recording", None), "timeline", {}).sample_timestamps) if hasattr(getattr(controller.recorder, "_recording", None), "timeline") and getattr(getattr(controller.recorder, "_recording", None), "timeline", None) is not None else "no-timeline")
        except Exception as exc:
            logger.error("Recorder toggle failed: %s", exc, exc_info=True)
            _video_debug("toggle_recording EXCEPTION %s", exc)
            self._emit_error(f"Recording toggle failed: {exc}")
            self._release_toggle()
            return
        finally:
            self._release_toggle_unless_finalizing()
            _video_debug("toggle_recording DONE is_recording=%s has_data=%s", getattr(controller.recorder, "is_recording", None), controller.recorder.has_recording_data() if controller.recorder else None)

    def toggle_pause_recording(self, checked: bool | None = None):
        del checked
        controller = self.controller
        if not controller.recorder.is_recording:
            self._sync_controls(
                is_recording=False,
                is_paused=False,
                pause_enabled=False,
            )
            return

        is_paused = controller.recorder.toggle_pause()
        self._sync_controls(
            is_recording=True,
            is_paused=is_paused,
            pause_enabled=True,
        )

    def open_video_editor(self, checked: bool = False):
        del checked
        controller = self.controller
        _video_debug(
            "open_video_editor called has_data=%s is_recording=%s finalize_in_progress=%s pending=%s presenter=%s plugin=%s",
            controller.recorder.has_recording_data() if controller.recorder else None,
            getattr(controller.recorder, "is_recording", None),
            controller._recording_finalize_in_progress,
            controller._pending_open_editor,
            controller.presenter,
            controller.video_editor_plugin,
        )
        if not controller.recorder.has_recording_data():
            rec = controller.recorder
            try:
                tl = getattr(getattr(rec, "_recording", None), "timeline", None)
                ts_len = len(getattr(tl, "sample_timestamps", [])) if tl else "no-timeline"
            except Exception:
                ts_len = "error"
            _video_debug(
                "open_video_editor REJECT: has_recording_data=False timeline_len=%s is_recording=%s finalize_in_progress=%s recorder=%s pending=%s",
                ts_len,
                getattr(rec, "is_recording", None),
                controller._recording_finalize_in_progress,
                rec,
                controller._pending_open_editor,
            )
            self._emit_error("No recording available to edit.")
            return

        if controller.recorder.is_recording:
            _video_debug("open_video_editor -> is_recording, set pending and stop recording")
            controller._pending_open_editor = True
            self.toggle_recording()
            return

        if controller._recording_finalize_in_progress:
            _video_debug("open_video_editor -> finalize in progress, set pending")
            controller._pending_open_editor = True
            return

        # Lazily ensure video_editor_plugin if deferred load happened after controller creation
        if controller.video_editor_plugin is None:
            try:
                from plugins.export.plugin import ExportPlugin  # type: ignore
                # Try to find ExportPlugin instance via plugin_coordinator
                coordinator = getattr(controller, "main_controller", None)
                coordinator = getattr(coordinator, "plugin_coordinator", None) if coordinator else getattr(controller, "event_bus", None)
                # Fallback: try global plugin_coordinator from context
                if hasattr(controller, "main_controller") and hasattr(controller.main_controller, "context"):
                    ctx = controller.main_controller.context
                    if hasattr(ctx, "plugin_coordinator") and ctx.plugin_coordinator:
                        plugin = ctx.plugin_coordinator.get_plugin("video_editor")
                        if plugin:
                            controller.video_editor_plugin = plugin
                            _video_debug("open_video_editor -> lazily resolved video_editor_plugin=%s", plugin)
                if controller.video_editor_plugin is None and hasattr(controller, "event_bus"):
                    # Try via ExportPlugin instance's own _ensure
                    try:
                        from core.plugin_system.registry import PluginRegistry  # type: ignore
                        pass
                    except Exception:
                        pass
            except Exception as exc:
                _video_debug("open_video_editor -> lazy resolve failed: %s", exc)

        if controller.presenter and hasattr(controller.presenter, "open_video_editor"):
            _video_debug(
                "open_video_editor -> presenter.open_video_editor snapshots=%s plugin=%s",
                len(controller.recorder.recording.timeline.sample_timestamps) if hasattr(controller.recorder.recording, "timeline") else "unknown",
                controller.video_editor_plugin,
            )
            controller.presenter.open_video_editor(
                controller.recorder.recording,
                controller,
                controller.video_editor_plugin,
            )
            return

        _video_debug("open_video_editor -> presenter unavailable presenter=%s, emit error", controller.presenter)
        self._emit_error("Video editor is unavailable.")

    def on_recording_finalized(self, _recording) -> None:
        _video_debug("on_recording_finalized pending=%s presenter=%s plugin=%s", self.controller._pending_open_editor, self.controller.presenter, self.controller.video_editor_plugin)
        controller = self.controller
        if (
            controller._pending_open_editor
            and controller.presenter
            and hasattr(controller.presenter, "open_video_editor")
            and controller.video_editor_plugin is not None
        ):
            _video_debug("on_recording_finalized -> opening editor")
            controller._pending_open_editor = False
            controller.presenter.open_video_editor(
                controller.recorder.recording,
                controller,
                controller.video_editor_plugin,
            )
        else:
            _video_debug("on_recording_finalized -> not opening (pending=%s)", controller._pending_open_editor)

    def on_recording_finalize_error(self, err) -> None:
        logger.error("Recording finalize failed: %s", err)
        self.controller._pending_open_editor = False

    def on_recording_finalize_finished(self) -> None:
        self._finish_finalize()

    def _finalize_recording_async(self) -> None:
        controller = self.controller
        if not self._begin_finalize():
            return

        worker = GenericWorker(controller.recorder.finalize_recording)
        worker.signals.result.connect(self.on_recording_finalized)
        worker.signals.error.connect(self.on_recording_finalize_error)
        worker.signals.finished.connect(self.on_recording_finalize_finished)
        controller.thread_pool.start(worker)

    def _sync_controls(
        self,
        *,
        is_recording: bool,
        is_paused: bool,
        pause_enabled: bool,
    ):
        controller = self.controller
        if controller.presenter and hasattr(controller.presenter, "sync_recording_controls"):
            controller.presenter.sync_recording_controls(
                is_recording=is_recording,
                is_paused=is_paused,
                pause_enabled=pause_enabled,
            )

    def _emit_error(self, message: str) -> None:
        _video_debug("_emit_error message=%r bus=%s has_error_signal=%s", message, self.controller.event_bus, hasattr(self.controller, "error_occurred"))
        controller = self.controller
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(message))
        else:
            try:
                controller.error_occurred.emit(message)
            except Exception as exc:
                _video_debug("_emit_error fallback failed: %s", exc)
                logger.warning("[video-editor-debug] _emit_error fallback failed: %s", exc)
