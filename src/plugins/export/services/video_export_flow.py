from __future__ import annotations

import logging
import tempfile

from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

def build_video_notification_preview(
    video_exporter,
    frames,
    resolution,
    options=None,
) -> str | None:
    try:
        if video_exporter is None:
            return None

        recording = (
            frames
            if hasattr(frames, "evaluate_at")
            else video_exporter._coerce_recording(frames)
        )
        if recording is None:
            return None

        snapshot = recording.evaluate_at(0.0)
        export_options = dict(options or {})
        fit_content = bool(export_options.get("fit_content", False))
        fill_rgba = (0, 0, 0, 0)
        fill_color = export_options.get("fit_content_fill_color")
        if isinstance(fill_color, str) and fill_color:
            from PySide6.QtGui import QColor

            qcolor = QColor(fill_color)
            fill_rgba = (
                qcolor.red(),
                qcolor.green(),
                qcolor.blue(),
                qcolor.alpha(),
            )

        global_bounds = None
        if fit_content:
            global_bounds = video_exporter.get_cached_global_bounds(recording, False)

        frame = video_exporter.render_snapshot_thumbnail_to_pil(
            snapshot,
            resolution[0],
            resolution[1],
            auto_crop=False,
            fit_content=fit_content,
            global_bounds=global_bounds,
            fill_color=fill_rgba,
        )
        if frame is None:
            return None

        max_dim = 256
        frame = frame.convert("RGBA")
        width, height = frame.size
        if max(width, height) > max_dim:
            scale = max_dim / max(width, height)
            frame = frame.resize((int(width * scale), int(height * scale)))

        thumb_file = tempfile.NamedTemporaryFile(
            prefix="imgsli_video_thumb_",
            suffix=".png",
            delete=False,
        )
        thumb_path = thumb_file.name
        thumb_file.close()
        frame.save(thumb_path, format="PNG")
        return thumb_path
    except Exception:
        return None

class VideoExportFlow:
    def __init__(self, controller):
        self.controller = controller

    @staticmethod
    def normalize_even_resolution(resolution: tuple[int, int]) -> tuple[int, int]:
        width, height = resolution
        safe_width = width if width % 2 == 0 else max(2, width - 1)
        safe_height = height if height % 2 == 0 else max(2, height - 1)
        return safe_width, safe_height

    def export_recorded_video(self, resolution=(1920, 1080), fps=60):
        controller = self.controller
        if (
            not controller.recorder.has_recording_data()
            or controller._recording_finalize_in_progress
        ):
            return

        worker = GenericWorker(
            controller.video_exporter.export_recorded_video, resolution, fps
        )
        worker.signals.result.connect(
            lambda path: logger.info("Export finished: %s", path)
        )
        worker.signals.error.connect(
            lambda err: logger.error("Export failed: %s", err)
        )
        controller.thread_pool.start(worker)

    def export_video_from_editor(
        self, frames, fps, resolution=(1920, 1080), options=None
    ):
        controller = self.controller
        safe_resolution = self.normalize_even_resolution(resolution)
        log_emit = None
        if hasattr(controller, "main_controller") and hasattr(
            controller.main_controller, "video_export_log"
        ):
            log_emit = controller.main_controller.video_export_log.emit

        def export_task(progress_callback):
            return controller.video_exporter.export_recorded_video(
                safe_resolution,
                fps,
                snapshots_override=frames,
                export_options=options,
                progress_callback=progress_callback,
                log_callback=log_emit,
            )

        worker = GenericWorker(export_task)
        export_completed = {"signaled": False}

        if hasattr(controller, "main_controller") and hasattr(
            controller.main_controller, "video_export_progress"
        ):
            worker.signals.progress.connect(
                controller.main_controller.video_export_progress.emit
            )
            worker.kwargs["progress_callback"] = worker.signals.progress

        def on_success(path):
            export_completed["signaled"] = True
            if path:
                logger.info("Video export finished: %s", path)
                if hasattr(controller, "main_controller") and hasattr(
                    controller.main_controller, "video_export_finished"
                ):
                    controller.main_controller.video_export_finished.emit(True)

                if controller.presenter and hasattr(
                    controller.presenter.main_window_app, "actions"
                ):
                    preview = build_video_notification_preview(
                        controller.video_exporter,
                        frames,
                        safe_resolution,
                        options,
                    )
                    controller.presenter.main_window_app.actions.notify_system(
                        "Video Exported",
                        f"Saved to: {path}",
                        image_path=preview,
                    )
            else:
                self._emit_export_finished(False)

        def on_error(err):
            export_completed["signaled"] = True
            logger.error("Video export failed: %s", err)
            self._emit_export_failed(f"Video export failed: {err}")
            self._emit_export_finished(False)

        def on_finished():
            if not export_completed["signaled"]:
                self._emit_export_finished(False)

        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)
        worker.signals.finished.connect(on_finished)
        controller.thread_pool.start(worker)

    def cancel_video_export(self):
        controller = self.controller
        if controller.video_exporter is not None:
            controller.video_exporter.request_cancel()

    def _emit_export_finished(self, success: bool) -> None:
        controller = self.controller
        if hasattr(controller, "main_controller") and hasattr(
            controller.main_controller, "video_export_finished"
        ):
            controller.main_controller.video_export_finished.emit(success)

    def _emit_export_failed(self, message: str) -> None:
        controller = self.controller
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(message))
        else:
            controller.error_occurred.emit(message)
