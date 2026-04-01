import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image
from PyQt6.QtGui import QColor

from core.store import Store
from plugins.export.scene_builder import ExportSceneBuilder
from plugins.export.services.gpu_export import _compute_canvas_plan
from plugins.video_editor.preview_gl import build_preview_store
from plugins.video_editor.services.export_config import ExportConfigBuilder
from plugins.video_editor.services.keyframes import KeyframedRecording
from shared.image_processing.pipeline import (
    RenderingPipeline,
    create_render_context_from_store,
)
from shared.image_processing.progressive_loader import load_full_image
from utils.resource_loader import get_magnifier_drawing_coords

logger = logging.getLogger("ImproveImgSLI")

VIDEO_EDITOR_AUTO_CROP = False

def _unique_video_path(directory, base_name, ext):
    full_path = os.path.join(directory, f"{base_name}.{ext}")
    if not os.path.exists(full_path):
        return full_path
    counter = 1
    while True:
        new_path = os.path.join(directory, f"{base_name} ({counter}).{ext}")
        if not os.path.exists(new_path):
            return new_path
        counter += 1

@dataclass(slots=True)
class VideoExportJob:
    recording: object
    output_path: str
    width: int
    height: int
    fps: int
    total_frames: int
    font_path: str | None
    fit_content: bool
    fill_rgba: tuple[int, int, int, int]
    global_bounds: tuple | None
    auto_crop: bool
    export_options: dict

@dataclass(slots=True)
class FrameTimingStats:
    evaluate_ms: float = 0.0
    render_ms: float = 0.0
    resize_ms: float = 0.0
    ffmpeg_write_ms: float = 0.0
    total_ms: float = 0.0
    frames: int = 0

    def add(
        self,
        *,
        evaluate_ms: float,
        render_ms: float,
        resize_ms: float,
        ffmpeg_write_ms: float,
        total_ms: float,
    ) -> None:
        self.evaluate_ms += evaluate_ms
        self.render_ms += render_ms
        self.resize_ms += resize_ms
        self.ffmpeg_write_ms += ffmpeg_write_ms
        self.total_ms += total_ms
        self.frames += 1

    def avg(self, value: float) -> float:
        return value / self.frames if self.frames else 0.0

class FFmpegCommandBuilder:
    def build(self, output_path, width, height, fps, options):
        ffmpeg_exe = "ffmpeg"
        if not shutil.which(ffmpeg_exe):
            local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg")
            if os.path.exists(local_ffmpeg) or os.path.exists(local_ffmpeg + ".exe"):
                ffmpeg_exe = local_ffmpeg
            else:
                raise FileNotFoundError(
                    "FFmpeg executable not found in PATH or app directory."
                )

        cmd = [
            ffmpeg_exe,
            "-y",
            "-loglevel",
            "warning",
            "-hide_banner",
            "-progress", "pipe:2",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{width}x{height}",
            "-pix_fmt",
            "rgba",
            "-r",
            str(fps),
            "-i",
            "-",
        ]

        if options.get("manual_mode", False):
            cmd.extend(shlex.split(options.get("manual_args", "").strip()))
            cmd.append(output_path)
            return cmd

        container = options.get("container", "mp4")
        codec = options.get("codec", "h264")
        quality_mode = options.get("quality_mode", "crf")
        crf = options.get("crf", 23)
        bitrate = options.get("bitrate", "5000k")
        preset = options.get("preset", "medium")
        pix_fmt = options.get("pix_fmt", "yuv420p")
        profile = ExportConfigBuilder.get_profile(codec)
        codec_family = profile.family
        ffmpeg_encoder = profile.ffmpeg_encoder
        is_hardware = profile.hardware

        if codec == "h264":
            cmd.extend(["-c:v", "libx264", "-preset", preset, "-pix_fmt", pix_fmt])
        elif codec == "h265":
            cmd.extend(["-c:v", "libx265", "-preset", preset, "-pix_fmt", pix_fmt])
        elif codec == "vp9":
            cmd.extend(["-c:v", "libvpx-vp9", "-row-mt", "1", "-pix_fmt", pix_fmt])
        elif codec == "av1":
            cmd.extend(["-c:v", "libaom-av1", "-cpu-used", "4", "-pix_fmt", pix_fmt])
        elif codec == "prores":
            profile_map = {
                "proxy": "0",
                "lt": "1",
                "standard": "2",
                "hq": "3",
                "4444": "4",
            }
            cmd.extend(
                [
                    "-c:v",
                    "prores_ks",
                    "-profile:v",
                    profile_map.get(preset, "2"),
                    "-pix_fmt",
                    pix_fmt,
                ]
            )
        elif codec == "gif":
            if preset == "Compact (Dithered)":
                cmd.extend(
                    [
                        "-vf",
                        "split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5",
                        "-c:v",
                        "gif",
                    ]
                )
            elif preset == "Balanced":
                cmd.extend(
                    [
                        "-vf",
                        "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse=dither=floyd_steinberg",
                        "-c:v",
                        "gif",
                    ]
                )
            else:
                cmd.extend(
                    [
                        "-vf",
                        "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                        "-c:v",
                        "gif",
                    ]
                )
        elif codec == "raw":
            cmd.extend(["-c:v", "rawvideo", "-pix_fmt", pix_fmt])
        elif is_hardware:
            cmd.extend(["-c:v", ffmpeg_encoder, "-pix_fmt", pix_fmt])
            if preset:
                if codec.endswith("_amf"):
                    cmd.extend(["-quality", preset])
                else:
                    cmd.extend(["-preset", preset])

        if codec_family not in ["prores", "gif", "raw"] and not is_hardware:
            if quality_mode == "crf":
                if codec_family == "vp9":
                    cmd.extend(["-b:v", "0", "-crf", str(crf)])
                else:
                    cmd.extend(["-crf", str(crf)])
            else:
                cmd.extend(["-b:v", bitrate])
        elif is_hardware:
            if codec.endswith("_nvenc") and quality_mode == "cq":
                cmd.extend(["-rc", "vbr", "-cq", str(crf), "-b:v", bitrate or "0"])
            else:
                cmd.extend(["-b:v", bitrate or "8000k"])

        cmd.append(output_path)
        return cmd

class FFmpegProcessManager:
    def __init__(self, active_processes: list[subprocess.Popen]):
        self._active_processes = active_processes
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []

    def start(self, cmd, stderr_line_callback=None):
        creation_flags = 0x08000000 if os.name == "nt" else 0
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
        )
        self._active_processes.append(process)
        self._stderr_lines = []

        def _emit_progress_block(block: dict):
            """Format a -progress key=value block into a single readable line."""
            parts = []
            if "frame" in block:
                parts.append(f"frame={block['frame']}")
            if "fps" in block:
                parts.append(f"fps={block['fps']}")
            if "total_size" in block:
                try:
                    size_kb = int(block["total_size"]) // 1024
                    parts.append(f"size={size_kb}kB")
                except ValueError:
                    pass
            if "out_time" in block:
                parts.append(f"time={block['out_time'].split('.')[0]}")
            if "speed" in block:
                parts.append(f"speed={block['speed']}")
            if parts and stderr_line_callback:
                try:
                    stderr_line_callback("  " + "  ".join(parts))
                except Exception:
                    pass

        def _drain_stderr():
            try:
                buf = b""
                progress_block: dict = {}
                while True:
                    chunk = process.stderr.read(512)
                    if not chunk:
                        break
                    buf += chunk
                    parts = buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
                    buf = parts[-1]
                    for part in parts[:-1]:
                        line = part.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        if "=" in line:
                            key, _, value = line.partition("=")
                            key = key.strip()
                            value = value.strip()
                            # progress=continue|end marks end of a block
                            if key == "progress":
                                if progress_block:
                                    _emit_progress_block(progress_block)
                                    progress_block = {}
                            else:
                                progress_block[key] = value
                        else:
                            # plain warning/error line from -loglevel warning
                            self._stderr_lines.append(line)
                            if stderr_line_callback:
                                try:
                                    stderr_line_callback(line)
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug("FFmpegProcessManager: stderr drain exception: %s", e, exc_info=True)

        self._stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        self._stderr_thread.start()
        return process

    def finalize(self, process) -> tuple[int | None, str]:
        self._detach(process)
        self._close_stdin(process)
        self._wait_for_process(process)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=10.0)
            self._stderr_thread = None
        stderr_text = "\n".join(self._stderr_lines)
        self._stderr_lines = []
        return process.returncode, stderr_text

    def cleanup(self):
        if not self._active_processes:
            return

        logger.info(
            f"Завершение {len(self._active_processes)} активных процессов ffmpeg..."
        )
        for process in self._active_processes[:]:
            if process.poll() is None:
                try:
                    logger.debug(f"Завершение процесса ffmpeg (PID: {process.pid})...")
                    process.terminate()
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"Процесс ffmpeg (PID: {process.pid}) не завершился, принудительно убиваем..."
                    )
                    process.kill()
                    process.wait()
                except Exception as e:
                    logger.error(
                        f"Ошибка при завершении процесса ffmpeg (PID: {process.pid}): {e}"
                    )
                    try:
                        process.kill()
                    except Exception:
                        pass

        self._active_processes.clear()
        logger.info("Все процессы ffmpeg завершены")

    def _detach(self, process):
        try:
            if process in self._active_processes:
                self._active_processes.remove(process)
        except Exception:
            pass

    @staticmethod
    def _close_stdin(process):
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass

    @staticmethod
    def _wait_for_process(process):
        try:
            process.wait(timeout=30.0)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg процесс все еще работает, пробуем завершить...")
            try:
                process.terminate()
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg не завершился, принудительно убиваем...")
                process.kill()
                process.wait()
            except Exception as e:
                logger.error(f"Ошибка при завершении процесса ffmpeg: {e}")
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Ошибка при ожидании завершения ffmpeg: {e}")
            try:
                process.kill()
                process.wait()
            except Exception:
                pass

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
                    f"FFmpeg процесс завершился неожиданно (код: {process.returncode})"
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
            except (BrokenPipeError, OSError) as e:
                logger.error(f"Ошибка записи в stdin процесса ffmpeg: {e}")
                return False
            write_ms = (time.perf_counter() - write_started) * 1000.0

            total_ms = timings["evaluate_ms"] + timings["render_ms"] + timings["resize_ms"] + write_ms
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
            frame_pil = frame_pil.resize(
                (job.width, job.height), Image.Resampling.BILINEAR
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
        self.images_cache = {}

        self._cached_global_bounds = None
        self._cached_bounds_snapshots_hash = None
        self._active_processes = []
        self._cancel_requested = False
        self._gpu_video_export_failed = False
        self._cpu_pipeline = None
        self._cpu_pipeline_font_path = None
        self._last_render_backend = "cpu"
        self._last_render_debug = {}
        self._scaled_pair_cache = {}
        self._ffmpeg_command_builder = FFmpegCommandBuilder()
        self._process_manager = FFmpegProcessManager(self._active_processes)
        self._render_loop = VideoRenderLoop(self)

    def _drain_last_render_debug(self) -> dict:
        data = self._last_render_debug
        self._last_render_debug = {}
        return data

    def _clear_frame_caches(self) -> None:
        self.images_cache.clear()
        self._scaled_pair_cache.clear()

    def _get_scaled_pair(
        self,
        image1,
        image2,
        width: int,
        height: int,
    ):
        key = (
            id(image1) if image1 is not None else 0,
            id(image2) if image2 is not None else 0,
            image1.size if image1 is not None else None,
            image2.size if image2 is not None else None,
            int(width),
            int(height),
        )
        cached = self._scaled_pair_cache.get(key)
        if cached is not None:
            return cached

        scaled = (
            image1.resize((width, height), Image.Resampling.BILINEAR),
            image2.resize((width, height), Image.Resampling.BILINEAR),
        )
        if len(self._scaled_pair_cache) >= 8:
            self._scaled_pair_cache.clear()
        self._scaled_pair_cache[key] = scaled
        return scaled

    @staticmethod
    def _get_gpu_tiling_config(width: int, height: int) -> tuple[bool, int]:
        pixel_count = max(1, int(width)) * max(1, int(height))
        max_dim = max(int(width), int(height))
        if pixel_count >= 24_000_000 or max_dim >= 5500:
            return True, 3
        if pixel_count >= 14_000_000 or max_dim >= 4096:
            return True, 2
        return False, 1

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
        return KeyframedRecording.from_snapshots(list(snapshots_or_recording or []))

    def _materialize_snapshots(self, snapshots_or_recording):
        if isinstance(snapshots_or_recording, Sequence):
            return list(snapshots_or_recording)
        if hasattr(snapshots_or_recording, "materialize_snapshots"):
            return snapshots_or_recording.materialize_snapshots()
        return []

    def calculate_global_canvas_bounds(self, snapshots, auto_crop=False):
        snapshots = self._materialize_snapshots(snapshots)
        if not snapshots:
            return None

        max_pad_left = 0
        max_pad_right = 0
        max_pad_top = 0
        max_pad_bottom = 0
        base_w, base_h = 0, 0

        for snap in snapshots:
            img1 = self._get_image(snap.image1_path, auto_crop)
            if img1:
                w, h = img1.size
                if w > base_w:
                    base_w = w
                if h > base_h:
                    base_h = h

            img2 = self._get_image(snap.image2_path, auto_crop)
            if img2:
                w, h = img2.size
                if w > base_w:
                    base_w = w
                if h > base_h:
                    base_h = h

        if base_w == 0 or base_h == 0:
            return None

        for snap in snapshots:
            if not snap.viewport_state.view_state.use_magnifier:
                continue

            img1 = self._get_image(snap.image1_path, auto_crop)
            img2 = self._get_image(snap.image2_path, auto_crop)

            if not img1 or not img2:
                continue

            temp_store = Store()

            temp_store.viewport = snap.viewport_state.clone()
            temp_store.settings = snap.settings_state.freeze_for_export()

            temp_store.viewport.session_data.image_state.image1 = img1
            temp_store.viewport.session_data.image_state.image2 = img2
            temp_store.document.full_res_image1 = img1
            temp_store.document.full_res_image2 = img2

            temp_store.viewport.geometry_state.pixmap_width = base_w
            temp_store.viewport.geometry_state.pixmap_height = base_h

            mag_coords = get_magnifier_drawing_coords(
                store=temp_store,
                drawing_width=base_w,
                drawing_height=base_h,
                container_width=base_w,
                container_height=base_h,
            )

            mag_rect = mag_coords[5]

            if mag_rect and not mag_rect.isNull():
                pad_left = max(0, -mag_rect.left())
                pad_right = max(0, mag_rect.right() - base_w)
                pad_top = max(0, -mag_rect.top())
                pad_bottom = max(0, mag_rect.bottom() - base_h)

                max_pad_left = max(max_pad_left, pad_left)
                max_pad_right = max(max_pad_right, pad_right)
                max_pad_top = max(max_pad_top, pad_top)
                max_pad_bottom = max(max_pad_bottom, pad_bottom)

        return (
            max_pad_left,
            max_pad_right,
            max_pad_top,
            max_pad_bottom,
            base_w,
            base_h,
        )

    def get_cached_global_bounds(self, snapshots, auto_crop=False):
        snapshots = self._materialize_snapshots(snapshots)
        if snapshots:
            current_hash = (len(snapshots), snapshots[-1].timestamp if snapshots else 0)
        else:
            current_hash = None

        if (
            self._cached_global_bounds is None
            or self._cached_bounds_snapshots_hash != current_hash
        ):
            self._cached_global_bounds = self.calculate_global_canvas_bounds(
                snapshots, auto_crop
            )
            self._cached_bounds_snapshots_hash = current_hash

        return self._cached_global_bounds

    def invalidate_bounds_cache(self):
        self._cached_global_bounds = None
        self._cached_bounds_snapshots_hash = None

    def _get_image(self, path, auto_crop=False):
        if not path or not os.path.exists(path):
            return None

        cache_key = (path, auto_crop)
        if cache_key in self.images_cache:
            return self.images_cache[cache_key]

        try:
            img = load_full_image(path, auto_crop=auto_crop)
            if img:
                self.images_cache[cache_key] = img
            return img
        except Exception as e:
            logger.error(f"Failed to load image for video: {path} - {e}")
            return None

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
        if self.gpu_export_service is not None and not self._gpu_video_export_failed:
            try:
                self._last_render_backend = "gpu"
                return self._render_snapshot_to_pil_gpu(
                    snap=snap,
                    out_w=out_w,
                    out_h=out_h,
                    auto_crop=auto_crop,
                    fit_content=fit_content,
                    global_bounds=global_bounds,
                    fill_color=fill_color,
                )
            except Exception as exc:
                self._gpu_video_export_failed = True
                self._last_render_backend = "cpu"
                logger.warning(
                    "GPU video render path failed, switching to CPU fallback: %s",
                    exc,
                )

        self._last_render_backend = "cpu"
        return self._render_snapshot_to_pil_cpu(
            snap=snap,
            out_w=out_w,
            out_h=out_h,
            font_path=font_path,
            auto_crop=auto_crop,
            fit_content=fit_content,
            global_bounds=global_bounds,
            fill_color=fill_color,
        )

    def _render_snapshot_to_pil_gpu(
        self,
        snap,
        out_w,
        out_h,
        auto_crop=False,
        fit_content=False,
        global_bounds=None,
        fill_color=(0, 0, 0, 0),
    ):
        debug = {}
        started = time.perf_counter()
        img1 = self._get_image(snap.image1_path, auto_crop)
        img2 = self._get_image(snap.image2_path, auto_crop)
        debug["load_ms"] = (time.perf_counter() - started) * 1000.0

        if not img1:
            img1 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (50, 50, 50, 255))
        if not img2:
            img2 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (80, 80, 80, 255))

        build_store_started = time.perf_counter()
        (
            temp_store,
            display_img1,
            display_img2,
            source_img1,
            source_img2,
            source_key,
        ) = build_preview_store(
            snap,
            img1,
            img2,
            fit_content=fit_content,
            global_bounds=global_bounds,
            fill_color=fill_color,
        )
        debug["build_store_ms"] = (time.perf_counter() - build_store_started) * 1000.0

        base_w, base_h = display_img1.size
        scale = min(out_w / base_w, out_h / base_h) if base_w > 0 and base_h > 0 else 1.0
        render_w = max(1, int(base_w * scale))
        render_h = max(1, int(base_h * scale))
        img_dest_x = (out_w - render_w) // 2
        img_dest_y = (out_h - render_h) // 2

        temp_store.viewport.geometry_state.pixmap_width = render_w
        temp_store.viewport.geometry_state.pixmap_height = render_h

        fit_resize_started = time.perf_counter()
        mag_coords = (
            get_magnifier_drawing_coords(
                store=temp_store,
                drawing_width=render_w,
                drawing_height=render_h,
                container_width=render_w,
                container_height=render_h,
            )
            if temp_store.viewport.view_state.use_magnifier
            else None
        )

        img1_s, img2_s = self._get_scaled_pair(
            display_img1,
            display_img2,
            render_w,
            render_h,
        )
        debug["fit_resize_ms"] = (time.perf_counter() - fit_resize_started) * 1000.0

        scene_ctx_started = time.perf_counter()
        scene_builder = ExportSceneBuilder(temp_store)
        render_context = scene_builder.build_render_context(
            img1_s,
            img2_s,
            source_image1=source_img1,
            source_image2=source_img2,
            source_key=source_key,
            magnifier_drawing_coords=mag_coords,
        )
        debug["scene_ctx_ms"] = (time.perf_counter() - scene_ctx_started) * 1000.0

        gpu_render_started = time.perf_counter()
        force_tiled, min_tiles_per_axis = self._get_gpu_tiling_config(out_w, out_h)
        frame_pil, gpu_debug = self.gpu_export_service.render_image(
            store=temp_store,
            render_context=render_context,
            force_tiled=force_tiled,
            min_tiles_per_axis=min_tiles_per_axis,
        )
        debug["gpu_render_ms"] = (time.perf_counter() - gpu_render_started) * 1000.0
        debug.update(gpu_debug)
        if frame_pil is None:
            final_frame = Image.new("RGBA", (out_w, out_h), fill_color)
            self._last_render_debug = debug
            return final_frame

        composite_started = time.perf_counter()
        canvas_plan = _compute_canvas_plan(
            temp_store,
            render_w,
            render_h,
            magnifier_drawing_coords=mag_coords,
        )
        pad_left = int(canvas_plan["padding_left"])
        pad_top = int(canvas_plan["padding_top"])
        crop_rect = (
            max(0, pad_left),
            max(0, pad_top),
            min(frame_pil.width, pad_left + render_w),
            min(frame_pil.height, pad_top + render_h),
        )
        base_image_content = frame_pil.crop(crop_rect)
        if base_image_content.size != (render_w, render_h):
            base_image_content = base_image_content.resize(
                (render_w, render_h), Image.Resampling.LANCZOS
            )

        if (
            img_dest_x == 0
            and img_dest_y == 0
            and base_image_content.size == (out_w, out_h)
        ):
            debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
            self._last_render_debug = debug
            return base_image_content

        final_frame = Image.new("RGBA", (out_w, out_h), fill_color)
        final_frame.alpha_composite(base_image_content, (img_dest_x, img_dest_y))
        debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
        self._last_render_debug = debug
        return final_frame

    def _get_cpu_pipeline(self, font_path: str | None) -> RenderingPipeline:
        font_path_str = font_path or ""
        if self._cpu_pipeline is None or self._cpu_pipeline_font_path != font_path_str:
            self._cpu_pipeline = RenderingPipeline(font_path)
            self._cpu_pipeline_font_path = font_path_str
        return self._cpu_pipeline

    def _render_snapshot_to_pil_cpu(
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
        debug = {}
        started = time.perf_counter()
        img1 = self._get_image(snap.image1_path, auto_crop)
        img2 = self._get_image(snap.image2_path, auto_crop)
        debug["load_ms"] = (time.perf_counter() - started) * 1000.0

        if not img1:
            img1 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (50, 50, 50, 255))
        if not img2:
            img2 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (80, 80, 80, 255))

        build_store_started = time.perf_counter()
        (
            temp_store,
            display_img1,
            display_img2,
            _source_img1,
            _source_img2,
            _source_key,
        ) = build_preview_store(
            snap,
            img1,
            img2,
            fit_content=fit_content,
            global_bounds=global_bounds,
            fill_color=fill_color,
        )
        debug["build_store_ms"] = (time.perf_counter() - build_store_started) * 1000.0

        base_w, base_h = display_img1.size
        scale = min(out_w / base_w, out_h / base_h) if base_w > 0 and base_h > 0 else 1.0
        render_w = max(1, int(base_w * scale))
        render_h = max(1, int(base_h * scale))
        img_dest_x = (out_w - render_w) // 2
        img_dest_y = (out_h - render_h) // 2

        temp_store.viewport.geometry_state.pixmap_width = render_w
        temp_store.viewport.geometry_state.pixmap_height = render_h

        fit_resize_started = time.perf_counter()
        mag_coords = (
            get_magnifier_drawing_coords(
                store=temp_store,
                drawing_width=render_w,
                drawing_height=render_h,
                container_width=render_w,
                container_height=render_h,
            )
            if temp_store.viewport.view_state.use_magnifier
            else None
        )

        img1_s, img2_s = self._get_scaled_pair(
            display_img1,
            display_img2,
            render_w,
            render_h,
        )
        debug["fit_resize_ms"] = (time.perf_counter() - fit_resize_started) * 1000.0

        scene_ctx_started = time.perf_counter()
        ctx = create_render_context_from_store(
            store=temp_store,
            width=render_w,
            height=render_h,
            magnifier_drawing_coords=mag_coords,
            image1_scaled=img1_s,
            image2_scaled=img2_s,
        )
        debug["scene_ctx_ms"] = (time.perf_counter() - scene_ctx_started) * 1000.0

        ctx.magnifier.is_interactive_mode = False
        ctx.images.file_name1 = snap.name1 or ""
        ctx.images.file_name2 = snap.name2 or ""

        pipeline = self._get_cpu_pipeline(font_path)
        cpu_render_started = time.perf_counter()
        frame_pil, p_l, p_t, _, _, _ = pipeline.render_frame(ctx)
        debug["cpu_render_ms"] = (time.perf_counter() - cpu_render_started) * 1000.0

        if not frame_pil:
            final_frame = Image.new("RGBA", (out_w, out_h), fill_color)
            self._last_render_debug = debug
            return final_frame

        composite_started = time.perf_counter()
        crop_rect = (
            max(0, p_l),
            max(0, p_t),
            min(frame_pil.width, p_l + render_w),
            min(frame_pil.height, p_t + render_h),
        )

        base_image_content = frame_pil.crop(crop_rect)

        if base_image_content.size != (render_w, render_h):
            base_image_content = base_image_content.resize(
                (render_w, render_h), Image.Resampling.LANCZOS
            )

        if (
            img_dest_x == 0
            and img_dest_y == 0
            and base_image_content.size == (out_w, out_h)
        ):
            debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
            self._last_render_debug = debug
            return base_image_content

        final_frame = Image.new("RGBA", (out_w, out_h), fill_color)
        final_frame.alpha_composite(base_image_content, (img_dest_x, img_dest_y))
        debug["composite_ms"] = (time.perf_counter() - composite_started) * 1000.0
        self._last_render_debug = debug

        return final_frame

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
        output_path = _unique_video_path(output_dir, base_name, ext)

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
            global_bounds = self.calculate_global_canvas_bounds(recording, auto_crop)
            if global_bounds:
                g_pad_left, g_pad_right, g_pad_top, g_pad_bottom, g_base_w, g_base_h = (
                    global_bounds
                )
                canvas_w = g_base_w + g_pad_left + g_pad_right
                canvas_h = g_base_h + g_pad_top + g_pad_bottom
                logger.info(
                    f"Global canvas size: {canvas_w}x{canvas_h} (base: {g_base_w}x{g_base_h}, padding: L={g_pad_left}, R={g_pad_right}, T={g_pad_top}, B={g_pad_bottom})"
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
        source = (
            snapshots_override if snapshots_override else self.recorder.snapshots
        )
        recording = self._coerce_recording(source)
        if not recording:
            return None

        self._cancel_requested = False
        self._gpu_video_export_failed = False

        if not export_options:
            export_options = {
                "container": "mp4",
                "codec": "h264",
                "quality_mode": "crf",
                "crf": 20,
                "preset": "medium",
            }

        job = self._build_export_job(recording, resolution, fps, export_options)
        logger.info(
            f"Rendering {job.total_frames} frames to {job.output_path} using FFmpeg..."
        )

        try:
            cmd = self._ffmpeg_command_builder.build(
                job.output_path, job.width, job.height, job.fps, job.export_options
            )
            logger.info(f"FFmpeg command: {' '.join(cmd)}")
            if log_callback:
                log_callback(f"$ {' '.join(cmd)}")
            process = self._process_manager.start(cmd, stderr_line_callback=log_callback)
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg or place ffmpeg.exe next to the application."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start FFmpeg: {e}") from e

        export_canceled = False
        stderr_output = ""
        process_returncode = None

        try:
            export_canceled = self._render_loop.render(process, job, progress_callback)
        except Exception as e:
            logger.error(f"Error during video rendering loop: {e}")
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

        logger.info(f"Video export successful: {job.output_path}")

        self._clear_frame_caches()
        return job.output_path

    def cleanup(self):
        self._process_manager.cleanup()
