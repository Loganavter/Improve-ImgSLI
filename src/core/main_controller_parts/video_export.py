from __future__ import annotations

import logging
import os
import tempfile

from sli_ui_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

def _generate_video_notification_preview(
    video_exporter,
    frames,
    resolution: tuple[int, int],
    options: dict | None = None,
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
            from PyQt6.QtGui import QColor

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

        frame = video_exporter.render_snapshot_to_pil(
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
        w, h = frame.size
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            frame = frame.resize((int(w * scale), int(h * scale)))
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
                if window_shell and hasattr(window_shell.main_window_app, "actions"):
                    preview_path = _generate_video_notification_preview(
                        video_exporter,
                        frames,
                        safe_resolution,
                        options,
                    )
                    window_shell.main_window_app.actions.notify_system(
                        "Video Exported", f"Saved to: {path}", image_path=preview_path
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
        return self.controller.video_exporter.get_image(path, auto_crop)

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
