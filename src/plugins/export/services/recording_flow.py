from __future__ import annotations

import logging

from core.events import CoreErrorOccurredEvent
from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class RecordingFlow:
    def __init__(self, controller):
        self.controller = controller

    def toggle_recording(self, checked: bool = None):
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
                    is_recording=False, is_paused=False, pause_enabled=False
                )
                self._finalize_recording_async()
            else:
                controller.recorder.start()
                self._sync_controls(
                    is_recording=True, is_paused=False, pause_enabled=True
                )
                controller._toggle_recording_in_progress = False
        finally:
            if controller.recorder.is_recording:
                controller._toggle_recording_in_progress = False

    def toggle_pause_recording(self, checked: bool = None):
        del checked
        controller = self.controller
        if not controller.recorder.is_recording:
            self._sync_controls(
                is_recording=False, is_paused=False, pause_enabled=False
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
        if not controller.recorder.has_recording_data():
            self._emit_error("No recording available to edit.")
            return

        if controller.recorder.is_recording:
            controller._pending_open_editor = True
            self.toggle_recording()
            return

        if controller._recording_finalize_in_progress:
            controller._pending_open_editor = True
            return

        if controller.presenter and hasattr(controller.presenter, "open_video_editor"):
            controller.presenter.open_video_editor(
                controller.recorder.recording,
                controller,
                controller.video_editor_plugin,
            )
            return

        self._emit_error("Video editor is unavailable.")

    def finalize_recording_async(self) -> None:
        self._finalize_recording_async()

    def on_recording_finalized(self, _recording) -> None:
        controller = self.controller
        if (
            controller._pending_open_editor
            and controller.presenter
            and hasattr(controller.presenter, "open_video_editor")
            and controller.video_editor_plugin is not None
        ):
            controller._pending_open_editor = False
            controller.presenter.open_video_editor(
                controller.recorder.recording,
                controller,
                controller.video_editor_plugin,
            )

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

    def _sync_controls(self, *, is_recording: bool, is_paused: bool, pause_enabled: bool):
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
