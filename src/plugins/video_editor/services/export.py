import logging
import os
import time
from collections.abc import Sequence

from PIL import Image
from PyQt6.QtGui import QColor

from plugins.video_editor.services.keyframing import KeyframedRecording
from plugins.video_editor.services.video_export_bounds import CanvasBoundsAnalyzer
from plugins.video_editor.services.video_export_encoding import (
    FFmpegCommandBuilder,
    FFmpegProcessManager,
)
from plugins.video_editor.services.video_export_images import VideoExportImageRepository
from plugins.video_editor.services.video_export_models import (
    FrameTimingStats,
    GlobalCanvasBounds,
    VideoExportJob,
    VideoRenderRequest,
    unique_video_path,
)
from plugins.video_editor.services.video_snapshot_rendering import SnapshotFrameRenderer

logger = logging.getLogger("ImproveImgSLI")

VIDEO_EDITOR_AUTO_CROP = False

class VideoRenderLoop:
    def __init__(self, exporter_service):
        self.exporter = exporter_service

    def render(self, process, job: VideoExportJob, progress_callback=None) -> bool:
        stats = FrameTimingStats()
        app_context = None
        if self.exporter.main_controller and hasattr(self.exporter.main_controller, "context"):
            app_context = self.exporter.main_controller.context

        for frame_idx in range(job.total_frames):
            if self.exporter._cancel_requested:
                logger.info("Video export canceled by user")
                return True

            if app_context and getattr(app_context, "_is_shutting_down", False):
                logger.warning("Экспорт видео прерван из-за завершения приложения")
                return True

            if process.poll() is not None:
                logger.warning(
                    "FFmpeg процесс завершился неожиданно (код: %s)",
                    process.returncode,
                )
                return False

            if progress_callback and frame_idx % 5 == 0:
                percent = int((frame_idx / job.total_frames) * 100)
                progress_callback.emit(percent)

            frame_pil, timings = self._render_frame(frame_idx, job)
            if not frame_pil:
                continue

            write_started = time.perf_counter()
            try:
                process.stdin.write(frame_pil.tobytes())
            except (BrokenPipeError, OSError) as exc:
                logger.error("Ошибка записи в stdin процесса ffmpeg: %s", exc)
                return False
            write_ms = (time.perf_counter() - write_started) * 1000.0

            total_ms = (
                timings["evaluate_ms"]
                + timings["render_ms"]
                + timings["resize_ms"]
                + write_ms
            )
            stats.add(
                evaluate_ms=timings["evaluate_ms"],
                render_ms=timings["render_ms"],
                resize_ms=timings["resize_ms"],
                ffmpeg_write_ms=write_ms,
                total_ms=total_ms,
            )
            self._log_frame_timing(frame_idx, job.total_frames, timings, write_ms, total_ms)

        if progress_callback and not self.exporter._cancel_requested:
            progress_callback.emit(100)
        self._log_summary(stats)
        return False

    def _render_frame(self, frame_idx: int, job: VideoExportJob):
        target_time = frame_idx / job.fps
        eval_started = time.perf_counter()
        snap = job.recording.evaluate_at(target_time)
        evaluate_ms = (time.perf_counter() - eval_started) * 1000.0

        render_started = time.perf_counter()
        frame_pil = self.exporter.render_snapshot_to_pil(
            snap,
            job.width,
            job.height,
            job.font_path,
            job.auto_crop,
            job.fit_content,
            job.global_bounds,
            job.fill_rgba,
        )
        render_ms = (time.perf_counter() - render_started) * 1000.0

        resize_ms = 0.0
        if frame_pil and frame_pil.size != (job.width, job.height):
            resize_started = time.perf_counter()
            frame_pil = frame_pil.resize((job.width, job.height), Image.Resampling.BILINEAR)
            resize_ms = (time.perf_counter() - resize_started) * 1000.0
        return frame_pil, {
            "evaluate_ms": evaluate_ms,
            "render_ms": render_ms,
            "resize_ms": resize_ms,
            "render_breakdown": self.exporter._drain_last_render_debug(),
        }

    def _log_frame_timing(self, frame_idx, total_frames, timings, write_ms, total_ms):
        if frame_idx < 3 or ((frame_idx + 1) % 30 == 0) or (frame_idx + 1 == total_frames):
            breakdown = timings.get("render_breakdown") or {}
            breakdown_parts = []
            for key in (
                "load_ms",
                "build_store_ms",
                "fit_resize_ms",
                "scene_ctx_ms",
                "canvas_plan_ms",
                "prepare_scene_images_ms",
                "widget_resize_show_ms",
                "configure_widget_ms",
                "paint_gl_ms",
                "grab_framebuffer_ms",
                "tiled_total_ms",
                "tiled_min_tiles_per_axis",
                "tile_columns",
                "tile_rows",
                "tile_width",
                "tile_height",
                "tile_resize_show_ms",
                "tile_paint_ms",
                "tile_grab_ms",
                "tile_paste_ms",
                "gpu_render_ms",
                "cpu_render_ms",
                "composite_ms",
            ):
                value = breakdown.get(key)
                if value is not None:
                    breakdown_parts.append(f"{key}={value:.1f}ms")
            breakdown_suffix = f" | {' '.join(breakdown_parts)}" if breakdown_parts else ""
            logger.info(
                "Video export frame %s/%s | eval=%.1fms render=%.1fms resize=%.1fms ffmpeg_write=%.1fms total=%.1fms backend=%s%s",
                frame_idx + 1,
                total_frames,
                timings["evaluate_ms"],
                timings["render_ms"],
                timings["resize_ms"],
                write_ms,
                total_ms,
                self.exporter._last_render_backend,
                breakdown_suffix,
            )

    def _log_summary(self, stats: FrameTimingStats):
        if not stats.frames:
            return
        logger.info(
            "Video export summary | frames=%s avg_eval=%.1fms avg_render=%.1fms avg_resize=%.1fms avg_ffmpeg_write=%.1fms avg_total=%.1fms backend=%s",
            stats.frames,
            stats.avg(stats.evaluate_ms),
            stats.avg(stats.render_ms),
            stats.avg(stats.resize_ms),
            stats.avg(stats.ffmpeg_write_ms),
            stats.avg(stats.total_ms),
            self.exporter._last_render_backend,
        )

class VideoExporterService:
    def __init__(self, recorder, store, main_controller=None, gpu_export_service=None):
        self.recorder = recorder
        self.main_store = store
        self.main_controller = main_controller
        self.gpu_export_service = gpu_export_service

        self._cached_global_bounds: GlobalCanvasBounds | None = None
        self._cached_bounds_snapshots_hash = None
        self._active_processes = []
        self._cancel_requested = False
        self._last_render_backend = "cpu"

        self._image_repository = VideoExportImageRepository()
        self._bounds_analyzer = CanvasBoundsAnalyzer(self._image_repository.get_image)
        self._frame_renderer = SnapshotFrameRenderer(
            image_loader=self._image_repository.get_image,
            gpu_export_service=self.gpu_export_service,
        )
        self._ffmpeg_command_builder = FFmpegCommandBuilder()
        self._process_manager = FFmpegProcessManager(self._active_processes)
        self._render_loop = VideoRenderLoop(self)

    def _drain_last_render_debug(self) -> dict:
        return self._frame_renderer.drain_last_debug()

    def _clear_frame_caches(self) -> None:
        self._image_repository.clear()

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
        bounds = self._bounds_analyzer.calculate(materialized, auto_crop)
        return bounds.as_tuple() if bounds is not None else None

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

        return (
            self._cached_global_bounds.as_tuple()
            if self._cached_global_bounds is not None
            else None
        )

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
        return GlobalCanvasBounds(*global_bounds)

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
        request = VideoRenderRequest(
            output_width=out_w,
            output_height=out_h,
            font_path=font_path,
            auto_crop=auto_crop,
            fit_content=fit_content,
            global_bounds=self._coerce_global_bounds(global_bounds),
            fill_rgba=fill_color,
        )
        result = self._frame_renderer.render(snap, request)
        self._last_render_backend = result.backend
        return result.image

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
