from __future__ import annotations

import logging

from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class VideoExportActions:
    def __init__(self, controller):
        self.controller = controller

    def export_video_from_editor(self, frames, fps, resolution=(1920, 1080), options=None):
        video_exporter = self.controller.video_exporter
        if not video_exporter:
            return

        width, height = resolution
        safe_resolution = (width + (width % 2), height + (height % 2))

        log_emit = self.controller.video_export_log.emit

        def export_task(progress_callback):
            return video_exporter.export_recorded_video(
                safe_resolution,
                fps,
                snapshots_override=frames,
                export_options=options,
                progress_callback=progress_callback,
                log_callback=log_emit,
            )

        worker = GenericWorker(export_task)
        export_completed = {"signaled": False}
        worker.signals.progress.connect(self.controller.video_export_progress.emit)
        worker.kwargs["progress_callback"] = worker.signals.progress

        def on_success(path):
            export_completed["signaled"] = True
            if path:
                logger.info("Video export finished: %s", path)
                self.controller.video_export_finished.emit(True)
                window_shell = self.controller.window_shell
                if window_shell and hasattr(window_shell.main_window_app, "notify_system"):
                    window_shell.main_window_app.notify_system(
                        "Video Exported", f"Saved to: {path}", image_path=None
                    )
            else:
                self.controller.video_export_finished.emit(False)

        def on_error(err):
            export_completed["signaled"] = True
            logger.error("Video export failed: %s", err)
            self.controller.error_occurred.emit(f"Video export failed: {err}")
            self.controller.video_export_finished.emit(False)

        def on_finished():
            if not export_completed["signaled"]:
                self.controller.video_export_finished.emit(False)

        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)
        worker.signals.finished.connect(on_finished)
        self.controller.thread_pool.start(worker)

    def get_video_export_image(self, path: str, auto_crop: bool = False):
        if not self.controller.video_exporter:
            return None
        return self.controller.video_exporter._get_image(path, auto_crop)

    def cancel_video_export(self):
        if self.controller.video_exporter:
            self.controller.video_exporter.request_cancel()

    def invalidate_video_export_bounds_cache(self):
        if self.controller.video_exporter:
            self.controller.video_exporter.invalidate_bounds_cache()

    def calculate_video_export_global_bounds(self, snapshots, auto_crop: bool = False):
        if not self.controller.video_exporter:
            return None
        return self.controller.video_exporter.calculate_global_canvas_bounds(
            snapshots, auto_crop
        )
