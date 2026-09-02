from __future__ import annotations

import logging

from core.events import CoreErrorOccurredEvent
from sli_ui_toolkit.workers import GenericWorker
from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def _video_debug(msg: str, *args, **kwargs) -> None:
    # Per-zone gated: only IMGSLI_VIDEO_EDITOR_DEBUG / IMGSLI_IC_VIDEO_DEBUG, not default --debug
    if _env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or _env_flag("IMGSLI_IC_VIDEO_DEBUG"):
        logger.warning("[video-editor-debug] " + msg, *args, **kwargs)
    else:
        logger.debug("[video-editor-debug] " + msg, *args, **kwargs)


def _video_enabled() -> bool:
    return _env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or _env_flag("IMGSLI_IC_VIDEO_DEBUG")


class RecordingFlow:
    def __init__(self, controller):
        self.controller = controller

    def toggle_recording(self, checked: bool | None = None):
        del checked
        controller = self.controller
        if (
            controller._toggle_recording_in_progress
            or controller._recording_finalize_in_progress
        ):
            return
        controller._toggle_recording_in_progress = True

        try:
            if controller.recorder.is_recording:
                controller.recorder.stop(finalize=False)
                self._sync_controls(
                    is_recording=False,
                    is_paused=False,
                    pause_enabled=False,
                )
                self._finalize_recording_async()
            else:
                controller.recorder.start()
                self._sync_controls(
                    is_recording=True,
                    is_paused=False,
                    pause_enabled=True,
                )
        except Exception as exc:
            logger.error("Recorder toggle failed: %s", exc, exc_info=True)
            self._emit_error(f"Recording toggle failed: {exc}")
            controller._toggle_recording_in_progress = False
            return
        finally:
            if not controller._recording_finalize_in_progress:
                controller._toggle_recording_in_progress = False

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
            _video_debug("open_video_editor -> no recording data, emit error")
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

        if controller.presenter and hasattr(controller.presenter, "open_video_editor"):
            _video_debug(
                "open_video_editor -> presenter.open_video_editor snapshots=%s",
                len(controller.recorder.recording.timeline.sample_timestamps) if hasattr(controller.recorder.recording, "timeline") else "unknown",
            )
            controller.presenter.open_video_editor(
                controller.recorder.recording,
                controller,
                controller.video_editor_plugin,
            )
            return

        _video_debug("open_video_editor -> presenter unavailable, emit error")
        self._emit_error("Video editor is unavailable.")

    def finalize_recording_async(self) -> None:
        self._finalize_recording_async()

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
        controller = self.controller
        controller._recording_finalize_in_progress = False
        controller._toggle_recording_in_progress = False

    def _finalize_recording_async(self) -> None:
        controller = self.controller
        if controller._recording_finalize_in_progress:
            return
        controller._recording_finalize_in_progress = True

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
        controller = self.controller
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(message))
        else:
            controller.error_occurred.emit(message)
