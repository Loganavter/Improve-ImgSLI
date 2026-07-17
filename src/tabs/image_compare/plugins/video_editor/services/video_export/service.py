from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence

from PySide6.QtGui import QColor

from plugins.export.services.gpu_export import GpuExportService
from shared.rendering import TargetSurfaceSpec
from tabs.image_compare.plugins.video_editor.services.keyframing import KeyframedRecording
from tabs.image_compare.plugins.video_editor.services.video_export.bounds import (
    CanvasBoundsAnalyzer,
)
from tabs.image_compare.plugins.video_editor.services.video_export.encoding import (
    FFmpegCommandBuilder,
    FFmpegProcessManager,
)
from tabs.image_compare.plugins.video_editor.services.video_export.images import (
    VideoExportImageRepository,
)
from tabs.image_compare.plugins.video_editor.services.video_export.models import (
    GlobalCanvasBounds,
    VideoExportJob,
    VideoRenderRequest,
    unique_video_path,
)
from tabs.image_compare.plugins.video_editor.services.video_export.render_loop import (
    VideoRenderLoop,
)
from tabs.image_compare.plugins.video_editor.services.video_snapshot_rendering import (
    SnapshotFrameRenderer,
)

logger = logging.getLogger("ImproveImgSLI")
_vrlog = logging.getLogger("ImproveImgSLI.video_render")

VIDEO_EDITOR_AUTO_CROP = False


class VideoExporterService:
    def __init__(self, recorder, store, main_controller=None, gpu_export_service=None):
        self.recorder = recorder
        self.main_store = store
        self.main_controller = main_controller
        self.gpu_export_service = gpu_export_service
        thumbnail_resource_manager = None
        if gpu_export_service is not None:
            thumbnail_resource_manager = getattr(
                getattr(gpu_export_service, "_proxy", None),
                "_resource_manager",
                None,
            )
        self._thumbnail_gpu_export_service = (
            GpuExportService(resource_manager=thumbnail_resource_manager)
            if gpu_export_service is not None
            else None
        )

        self._cached_global_bounds: GlobalCanvasBounds | None = None
        self._cached_bounds_snapshots_hash = None
        self._active_processes = []
        self._cancel_requested = False
        self._last_render_backend = "gpu"

        self._image_repository = VideoExportImageRepository()
        self._bounds_analyzer = CanvasBoundsAnalyzer(self._image_repository.get_image)
        self._frame_renderer = SnapshotFrameRenderer(
            image_loader=self._image_repository.get_image,
            gpu_export_service=self.gpu_export_service,
        )
        self._thumbnail_frame_renderer = SnapshotFrameRenderer(
            image_loader=self._image_repository.get_image,
            gpu_export_service=self._thumbnail_gpu_export_service,
        )
        self._ffmpeg_command_builder = FFmpegCommandBuilder()
        self._process_manager = FFmpegProcessManager(self._active_processes)
        self._render_loop = VideoRenderLoop(self)

    def _drain_last_render_debug(self) -> dict:
        return self._frame_renderer.drain_last_debug()

    def _clear_frame_caches(self) -> None:
        self._image_repository.clear()
        self._frame_renderer.reset_backend_state()
        self._thumbnail_frame_renderer.reset_backend_state()

    def request_cancel(self):
        self._cancel_requested = True
        self.cleanup()

    def _coerce_recording(self, snapshots_or_recording):
        if isinstance(snapshots_or_recording, KeyframedRecording):
            return snapshots_or_recording
        if hasattr(snapshots_or_recording, "evaluate_at") and hasattr(
            snapshots_or_recording, "get_duration"
        ):
            return snapshots_or_recording
        extra_adapters = tuple(getattr(snapshots_or_recording, "extra_adapters", ()))
        return KeyframedRecording.from_snapshots(
            list(snapshots_or_recording or []),
            extra_adapters=extra_adapters,
        )

    def _materialize_snapshots(self, snapshots_or_recording):
        if isinstance(snapshots_or_recording, Sequence):
            return list(snapshots_or_recording)
        if hasattr(snapshots_or_recording, "materialize_snapshots"):
            return snapshots_or_recording.materialize_snapshots()
        return []

    def calculate_global_canvas_bounds(self, snapshots, auto_crop=False):
        materialized = self._materialize_snapshots(snapshots)
        return self._bounds_analyzer.calculate(materialized, auto_crop)

    def get_cached_global_bounds(self, snapshots, auto_crop=False):
        materialized = self._materialize_snapshots(snapshots)
        current_hash = (
            (len(materialized), materialized[-1].timestamp if materialized else 0)
            if materialized
            else None
        )

        if (
            self._cached_global_bounds is None
            or self._cached_bounds_snapshots_hash != current_hash
        ):
            self._cached_global_bounds = self._bounds_analyzer.calculate(
                materialized,
                auto_crop,
            )
            self._cached_bounds_snapshots_hash = current_hash

        return self._cached_global_bounds

    def invalidate_bounds_cache(self):
        self._cached_global_bounds = None
        self._cached_bounds_snapshots_hash = None

    def get_image(self, path, auto_crop=False):
        return self._image_repository.get_image(path, auto_crop)

    def _get_image(self, path, auto_crop=False):
        return self.get_image(path, auto_crop)

    @staticmethod
    def _coerce_global_bounds(global_bounds) -> GlobalCanvasBounds | None:
        if global_bounds is None:
            return None
        if isinstance(global_bounds, GlobalCanvasBounds):
            return global_bounds
        raise TypeError("global_bounds must be GlobalCanvasBounds or None")

    @staticmethod
    def _build_render_request(
        out_w,
        out_h,
        font_path,
        auto_crop,
        fit_content,
        global_bounds,
        fill_color,
    ) -> VideoRenderRequest:
        return VideoRenderRequest(
            target_surface=TargetSurfaceSpec(
                width=max(1, int(out_w)),
                height=max(1, int(out_h)),
                fill_rgba=fill_color,
            ),
            font_path=font_path,
            auto_crop=auto_crop,
            fit_content=fit_content,
            global_bounds=global_bounds,
        )

    def _render_snapshot_with_renderer(self, renderer, snap, request: VideoRenderRequest):
        _vrlog.debug(
            "render_begin renderer=%s out=%sx%s fit_content=%s ts=%s",
            "thumbnail" if renderer is self._thumbnail_frame_renderer else "main",
            request.target_surface.width,
            request.target_surface.height,
            request.fit_content,
            getattr(snap, "timestamp", None),
        )
        result = renderer.render(snap, request)
        _vrlog.debug(
            "render_done renderer=%s out=%sx%s backend=%s",
            "thumbnail" if renderer is self._thumbnail_frame_renderer else "main",
            request.target_surface.width,
            request.target_surface.height,
            result.backend,
        )
        self._last_render_backend = result.backend
        return result.image

    def prepare_snapshot_canvas_frame(
        self,
        snap,
        out_w,
        out_h,
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
        *,
        thumbnail: bool = False,
    ):
        request = self._build_render_request(
            out_w,
            out_h,
            font_path,
            auto_crop,
            fit_content,
            self._coerce_global_bounds(global_bounds),
            fill_color,
        )
        renderer = self._thumbnail_frame_renderer if thumbnail else self._frame_renderer
        return renderer.prepare_canvas_frame(snap, request)

    def render_snapshot_to_pil(
        self,
        snap,
        out_w,
        out_h,
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
    ):
        request = self._build_render_request(
            out_w,
            out_h,
            font_path,
            auto_crop,
            fit_content,
            self._coerce_global_bounds(global_bounds),
            fill_color,
        )
        return self._render_snapshot_with_renderer(self._frame_renderer, snap, request)

    def render_snapshot_thumbnail_to_pil(
        self,
        snap,
        out_w,
        out_h,
        font_path=None,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
    ):
        request = self._build_render_request(
            out_w,
            out_h,
            font_path,
            auto_crop,
            fit_content,
            self._coerce_global_bounds(global_bounds),
            fill_color,
        )
        return self._render_snapshot_with_renderer(
            self._thumbnail_frame_renderer,
            snap,
            request,
        )

    def _build_export_job(self, recording, resolution, fps, export_options):
        out_w, out_h = resolution

        custom_dir = export_options.get("output_dir", "").strip()
        custom_name = export_options.get("file_name", "").strip()
        output_dir = (
            custom_dir
            if custom_dir
            else (self.main_store.settings.export_default_dir or os.getcwd())
        )

        ext = export_options.get("container", "mp4")
        if export_options.get("manual_mode") and not ext:
            ext = "mp4"

        if custom_name:
            base_name = (
                custom_name[: -len(f".{ext}")]
                if custom_name.lower().endswith(f".{ext}")
                else custom_name
            )
        else:
            base_name = f"video_{int(time.time())}"

        os.makedirs(output_dir, exist_ok=True)
        output_path = unique_video_path(output_dir, base_name, ext)

        font_path = None
        window_shell = self.main_controller.window_shell if self.main_controller else None
        if window_shell is not None:
            font_path = window_shell.main_window_app.font_path_absolute

        total_duration = recording.get_duration()
        total_frames = max(1, int(total_duration * fps))

        fit_content = export_options.get("fit_content", False)
        fill_color = QColor(export_options.get("fit_content_fill_color", "#00000000"))
        fill_rgba = (
            fill_color.red(),
            fill_color.green(),
            fill_color.blue(),
            fill_color.alpha(),
        )
        auto_crop = VIDEO_EDITOR_AUTO_CROP

        global_bounds = None
        if fit_content:
            logger.info("Calculating global canvas bounds for fit_content mode...")
            global_bounds = self._bounds_analyzer.calculate(
                self._materialize_snapshots(recording),
                auto_crop,
            )
            if global_bounds:
                canvas_w = (
                    global_bounds.base_width
                    + global_bounds.pad_left
                    + global_bounds.pad_right
                )
                canvas_h = (
                    global_bounds.base_height
                    + global_bounds.pad_top
                    + global_bounds.pad_bottom
                )
                logger.info(
                    "Global canvas size: %sx%s (base: %sx%s, padding: L=%s, R=%s, T=%s, B=%s)",
                    canvas_w,
                    canvas_h,
                    global_bounds.base_width,
                    global_bounds.base_height,
                    global_bounds.pad_left,
                    global_bounds.pad_right,
                    global_bounds.pad_top,
                    global_bounds.pad_bottom,
                )

        return VideoExportJob(
            recording=recording,
            output_path=output_path,
            width=out_w,
            height=out_h,
            fps=fps,
            total_frames=total_frames,
            font_path=font_path,
            fit_content=fit_content,
            fill_rgba=fill_rgba,
            global_bounds=global_bounds,
            auto_crop=auto_crop,
            export_options=export_options,
        )

    def export_recorded_video(
        self,
        resolution=(1920, 1080),
        fps=60,
        snapshots_override=None,
        export_options=None,
        progress_callback=None,
        log_callback=None,
    ):
        source = snapshots_override if snapshots_override else self.recorder.snapshots
        recording = self._coerce_recording(source)
        if not recording:
            return None

        self._cancel_requested = False
        self._frame_renderer.reset_backend_state()
        self._thumbnail_frame_renderer.reset_backend_state()

        if not export_options:
            export_options = {
                "container": "mp4",
                "codec": "h264",
                "quality_mode": "crf",
                "crf": 20,
                "preset": "medium",
            }

        job = self._build_export_job(recording, resolution, fps, export_options)
        logger.info("Rendering %s frames to %s using FFmpeg...", job.total_frames, job.output_path)

        try:
            cmd = self._ffmpeg_command_builder.build(
                job.output_path, job.width, job.height, job.fps, job.export_options
            )
            logger.info("FFmpeg command: %s", " ".join(cmd))
            if log_callback:
                log_callback(f"$ {' '.join(cmd)}")
            process = self._process_manager.start(cmd, stderr_line_callback=log_callback)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg or place ffmpeg.exe next to the application."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to start FFmpeg: {exc}") from exc

        export_canceled = False
        stderr_output = ""
        process_returncode = None

        try:
            export_canceled = self._render_loop.render(process, job, progress_callback)
        except Exception as exc:
            logger.error("Error during video rendering loop: %s", exc)
        finally:
            process_returncode, stderr_output = self._process_manager.finalize(process)

        if self._cancel_requested or export_canceled:
            self._clear_frame_caches()
            return None

        if process_returncode != 0:
            error_msg = f"FFmpeg exited with error code {process_returncode}"
            if stderr_output:
                error_msg += f"\n\n{stderr_output.strip()}"
            self._clear_frame_caches()
            raise RuntimeError(error_msg)

        logger.info("Video export successful: %s", job.output_path)
        self._clear_frame_caches()
        return job.output_path

    def cleanup(self):
        self._process_manager.cleanup()
        if self._thumbnail_gpu_export_service is not None:
            self._thumbnail_gpu_export_service.shutdown()
