from __future__ import annotations

import logging
import queue
import threading
import time

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.video_export.models import (
    FrameTimingStats,
    VideoExportJob,
)

logger = logging.getLogger("ImproveImgSLI")


def _contain_resize_rgba(
    frame: Image.Image,
    width: int,
    height: int,
    fill_rgba: tuple[int, int, int, int],
) -> Image.Image:
    """Scale ``frame`` into ``width``×``height`` without changing aspect ratio."""
    tw, th = max(1, int(width)), max(1, int(height))
    sw, sh = frame.size
    if (sw, sh) == (tw, th):
        return frame
    scale = min(tw / max(1, sw), th / max(1, sh))
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    scaled = frame.resize((nw, nh), Image.Resampling.BILINEAR)
    if (nw, nh) == (tw, th):
        return scaled
    canvas = Image.new("RGBA", (tw, th), fill_rgba)
    canvas.paste(scaled, ((tw - nw) // 2, (th - nh) // 2), scaled)
    return canvas


class VideoRenderLoop:
    def __init__(self, exporter_service):
        self.exporter = exporter_service

    def render(self, process, job: VideoExportJob, progress_callback=None) -> bool:
        """Pipelined render/write:
        - Producer (this thread): renders frame N+1 while writer drains N.
        - Consumer (writer thread): blocking-writes RGBA bytes to ffmpeg stdin.
        - Bounded queue gives back-pressure so memory stays bounded under slow
          encoders, while still overlapping the sync grab stall with the
          previous frame's ffmpeg-write cost.
        """
        stats = FrameTimingStats()
        app_context = None
        if self.exporter.main_controller and hasattr(self.exporter.main_controller, "context"):
            app_context = self.exporter.main_controller.context

        # Sentinel to mark end of stream.
        END_OF_STREAM = object()
        # capacity 2 = at most 1 frame buffered while the next is rendering and
        # one is being written; tuneable, but bigger doesn't help (the next
        # render still has to wait for grab anyway).
        frame_queue: "queue.Queue" = queue.Queue(maxsize=2)
        writer_error: list = []
        writer_write_times: list = []

        def writer_loop():
            while True:
                item = frame_queue.get()
                if item is END_OF_STREAM:
                    return
                payload = item
                write_started = time.perf_counter()
                try:
                    process.stdin.write(payload)
                except (BrokenPipeError, OSError) as exc:
                    logger.error("Ошибка записи в stdin процесса ffmpeg: %s", exc)
                    writer_error.append(exc)
                    # Drain remaining items to unblock producer.
                    while True:
                        nxt = frame_queue.get()
                        if nxt is END_OF_STREAM:
                            return
                else:
                    writer_write_times.append(
                        (time.perf_counter() - write_started) * 1000.0
                    )

        writer_thread = threading.Thread(
            target=writer_loop, name="ffmpeg-writer", daemon=True
        )
        writer_thread.start()

        try:
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

                if writer_error:
                    return False

                if progress_callback and frame_idx % 5 == 0:
                    percent = int((frame_idx / job.total_frames) * 100)
                    progress_callback.emit(percent)

                frame_pil, timings = self._render_frame(frame_idx, job)
                if not frame_pil:
                    continue

                # See note on _raw_rgba_bytes in gpu_export_proxy: when no
                # resize/composite happened we already hold the contiguous RGBA
                # bytes; writing them directly skips a PIL.tobytes() memcpy.
                raw_bytes = getattr(frame_pil, "_raw_rgba_bytes", None)
                payload = raw_bytes if raw_bytes is not None else frame_pil.tobytes()

                # enqueue_started → enqueue_finished measures producer-side
                # back-pressure: how long we wait because the writer hasn't
                # drained the previous frame yet. Under good pipelining this
                # should be ~0; under encoder backpressure it converges to the
                # ffmpeg-bound write time.
                enqueue_started = time.perf_counter()
                frame_queue.put(payload)
                enqueue_ms = (time.perf_counter() - enqueue_started) * 1000.0

                total_ms = (
                    timings["evaluate_ms"]
                    + timings["render_ms"]
                    + timings["resize_ms"]
                    + timings.get("prescale_ms", 0.0)
                    + enqueue_ms
                )
                stats.add(
                    evaluate_ms=timings["evaluate_ms"],
                    render_ms=timings["render_ms"],
                    resize_ms=timings["resize_ms"],
                    ffmpeg_write_ms=enqueue_ms,
                    total_ms=total_ms,
                )
                self._log_frame_timing(
                    frame_idx, job.total_frames, timings, enqueue_ms, total_ms
                )

            if progress_callback and not self.exporter._cancel_requested:
                progress_callback.emit(100)
        finally:
            frame_queue.put(END_OF_STREAM)
            writer_thread.join()

        if writer_error:
            return False
        self._log_summary(stats, writer_write_times)
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
            # Contain-fit into the job framebuffer. A bilinear stretch here is
            # how 4:3 snapshot frames became fat 16:9 when geometry pads were
            # dropped earlier in prepare.
            resize_started = time.perf_counter()
            frame_pil = _contain_resize_rgba(
                frame_pil, job.width, job.height, job.fill_rgba
            )
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
                "prescale_ms",
                "build_store_ms",
                "fit_resize_ms",
                "scene_ctx_ms",
                "canvas_plan_ms",
                "prepare_scene_images_ms",
                "widget_resize_show_ms",
                "configure_widget_ms",
                "paint_gl_ms",
                "grab_framebuffer_ms",
                "grab_raw_ms",
                "qimage_convert_ms",
                "qimage_bits_ms",
                "pil_frombytes_ms",
                "pil_resize_ms",
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

    def _log_summary(self, stats: FrameTimingStats, writer_write_times=None):
        if not stats.frames:
            return
        # In pipelined mode `ffmpeg_write_ms` reports the producer's enqueue
        # time (~0 when the queue is empty), so it no longer maps to the actual
        # ffmpeg write cost. Report the writer-thread-measured timings
        # separately so the summary still tells the operator if the encoder is
        # the bottleneck.
        writer_avg = 0.0
        if writer_write_times:
            writer_avg = sum(writer_write_times) / float(len(writer_write_times))
        logger.info(
            "Video export summary | frames=%s avg_eval=%.1fms avg_render=%.1fms "
            "avg_resize=%.1fms avg_enqueue=%.1fms avg_ffmpeg_write=%.1fms "
            "avg_total=%.1fms backend=%s",
            stats.frames,
            stats.avg(stats.evaluate_ms),
            stats.avg(stats.render_ms),
            stats.avg(stats.resize_ms),
            stats.avg(stats.ffmpeg_write_ms),
            writer_avg,
            stats.avg(stats.total_ms),
            self.exporter._last_render_backend,
        )
