import logging
import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Sequence

from PIL import Image
from PyQt6.QtGui import QColor

from core.store import Store
from plugins.video_editor.preview_gl import build_preview_store
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

class VideoExporterService:
    def __init__(self, recorder, store, main_controller=None):
        self.recorder = recorder
        self.main_store = store
        self.main_controller = main_controller
        self.images_cache = {}

        self._cached_global_bounds = None
        self._cached_bounds_snapshots_hash = None
        self._active_processes = []
        self._cancel_requested = False

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
            if not snap.viewport_state.use_magnifier:
                continue

            img1 = self._get_image(snap.image1_path, auto_crop)
            img2 = self._get_image(snap.image2_path, auto_crop)

            if not img1 or not img2:
                continue

            temp_store = Store()

            temp_store.viewport = snap.viewport_state.clone()
            temp_store.settings = snap.settings_state.freeze_for_export()

            temp_store.viewport.image1 = img1
            temp_store.viewport.image2 = img2
            temp_store.document.full_res_image1 = img1
            temp_store.document.full_res_image2 = img2

            temp_store.viewport.pixmap_width = base_w
            temp_store.viewport.pixmap_height = base_h

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

        export_canceled = False
        stderr_output = ""

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
        img1 = self._get_image(snap.image1_path, auto_crop)
        img2 = self._get_image(snap.image2_path, auto_crop)

        if not img1:
            img1 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (50, 50, 50, 255))
        if not img2:
            img2 = Image.new("RGBA", (max(1, out_w), max(1, out_h)), (80, 80, 80, 255))

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

        base_w, base_h = display_img1.size
        scale = min(out_w / base_w, out_h / base_h) if base_w > 0 and base_h > 0 else 1.0
        render_w = max(1, int(base_w * scale))
        render_h = max(1, int(base_h * scale))
        img_dest_x = (out_w - render_w) // 2
        img_dest_y = (out_h - render_h) // 2

        temp_store.viewport.pixmap_width = render_w
        temp_store.viewport.pixmap_height = render_h

        mag_coords = (
            get_magnifier_drawing_coords(
                store=temp_store,
                drawing_width=render_w,
                drawing_height=render_h,
                container_width=render_w,
                container_height=render_h,
            )
            if temp_store.viewport.use_magnifier
            else None
        )

        img1_s = display_img1.resize((render_w, render_h), Image.Resampling.BILINEAR)
        img2_s = display_img2.resize((render_w, render_h), Image.Resampling.BILINEAR)

        ctx = create_render_context_from_store(
            store=temp_store,
            width=render_w,
            height=render_h,
            magnifier_drawing_coords=mag_coords,
            image1_scaled=img1_s,
            image2_scaled=img2_s,
        )

        ctx.is_interactive_mode = False
        ctx.file_name1 = snap.name1
        ctx.file_name2 = snap.name2

        pipeline = RenderingPipeline(font_path)
        frame_pil, p_l, p_t, _, _, _ = pipeline.render_frame(ctx)

        final_frame = Image.new("RGBA", (out_w, out_h), fill_color)

        if not frame_pil:
            return final_frame

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

        final_frame.alpha_composite(base_image_content, (img_dest_x, img_dest_y))

        return final_frame

    def _build_ffmpeg_command(self, output_path, width, height, fps, options):
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
            "error",
            "-hide_banner",
            "-nostats",
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
            user_args = shlex.split(options.get("manual_args", "").strip())
            cmd.extend(user_args)
        else:
            container = options.get("container", "mp4")
            codec = options.get("codec", "h264")
            quality_mode = options.get("quality_mode", "crf")
            crf = options.get("crf", 23)
            bitrate = options.get("bitrate", "5000k")
            preset = options.get("preset", "medium")
            pix_fmt = options.get("pix_fmt", "yuv420p")

            if codec == "h264":
                cmd.extend(
                    ["-c:v", "libx264", "-preset", preset, "-pix_fmt", pix_fmt]
                )
            elif codec == "h265":
                cmd.extend(
                    ["-c:v", "libx265", "-preset", preset, "-pix_fmt", pix_fmt]
                )
            elif codec == "vp9":
                cmd.extend(
                    ["-c:v", "libvpx-vp9", "-row-mt", "1", "-pix_fmt", pix_fmt]
                )
            elif codec == "av1":
                cmd.extend(
                    ["-c:v", "libaom-av1", "-cpu-used", "4", "-pix_fmt", pix_fmt]
                )
            elif codec == "prores":
                profile_map = {
                    "proxy": "0",
                    "lt": "1",
                    "standard": "2",
                    "hq": "3",
                    "4444": "4",
                }
                profile_val = profile_map.get(preset, "2")
                cmd.extend(
                    [
                        "-c:v",
                        "prores_ks",
                        "-profile:v",
                        profile_val,
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

            if codec not in ["prores", "gif", "raw"]:
                if quality_mode == "crf":
                    if codec == "vp9":
                        cmd.extend(["-b:v", "0", "-crf", str(crf)])
                    else:
                        cmd.extend(["-crf", str(crf)])
                else:
                    cmd.extend(["-b:v", bitrate])

        cmd.append(output_path)
        return cmd

    def export_recorded_video(
        self,
        resolution=(1920, 1080),
        fps=60,
        snapshots_override=None,
        export_options=None,
        progress_callback=None,
    ):
        source = (
            snapshots_override if snapshots_override else self.recorder.snapshots
        )
        recording = self._coerce_recording(source)
        if not recording:
            return None

        self._cancel_requested = False

        if not export_options:
            export_options = {
                "container": "mp4",
                "codec": "h264",
                "quality_mode": "crf",
                "crf": 20,
                "preset": "medium",
            }

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
            if custom_name.lower().endswith(f".{ext}"):
                base_name = custom_name[: -len(f".{ext}")]
            else:
                base_name = custom_name
        else:
            base_name = f"video_{int(time.time())}"

        video_path = _unique_video_path(output_dir, base_name, ext)

        os.makedirs(output_dir, exist_ok=True)

        font_path = None
        if (
            self.main_controller
            and hasattr(self.main_controller, "presenter")
            and self.main_controller.presenter
        ):
            font_path = (
                self.main_controller.presenter.main_window_app.font_path_absolute
            )

        total_duration = recording.get_duration()

        total_frames = int(total_duration * fps)
        if total_frames == 0:
            total_frames = 1

        logger.info(f"Rendering {total_frames} frames to {video_path} using FFmpeg...")

        try:
            cmd = self._build_ffmpeg_command(
                video_path, out_w, out_h, fps, export_options
            )
            logger.info(f"FFmpeg command: {' '.join(cmd)}")

            creation_flags = 0x08000000 if os.name == "nt" else 0

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags,
            )

            self._active_processes.append(process)
        except FileNotFoundError:
            logger.error("FFmpeg not found. Please install FFmpeg.")
            return None
        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            return None

        fit_content = export_options.get("fit_content", False)
        fill_color_hex = export_options.get("fit_content_fill_color", "#00000000")
        fill_color = QColor(fill_color_hex)
        fill_rgba = (
            fill_color.red(),
            fill_color.green(),
            fill_color.blue(),
            fill_color.alpha(),
        )
        should_crop = VIDEO_EDITOR_AUTO_CROP

        global_bounds = None
        if fit_content:
            logger.info("Calculating global canvas bounds for fit_content mode...")
            global_bounds = self.calculate_global_canvas_bounds(recording, should_crop)
            if global_bounds:
                g_pad_left, g_pad_right, g_pad_top, g_pad_bottom, g_base_w, g_base_h = (
                    global_bounds
                )

                canvas_w = g_base_w + g_pad_left + g_pad_right
                canvas_h = g_base_h + g_pad_top + g_pad_bottom
                logger.info(
                    f"Global canvas size: {canvas_w}x{canvas_h} (base: {g_base_w}x{g_base_h}, padding: L={g_pad_left}, R={g_pad_right}, T={g_pad_top}, B={g_pad_bottom})"
                )

        export_canceled = False

        try:

            app_context = None
            if self.main_controller and hasattr(self.main_controller, "context"):
                app_context = self.main_controller.context

            for frame_idx in range(total_frames):
                if self._cancel_requested:
                    logger.info("Video export canceled by user")
                    export_canceled = True
                    break

                if app_context and getattr(app_context, "_is_shutting_down", False):
                    logger.warning("Экспорт видео прерван из-за завершения приложения")
                    break

                if process.poll() is not None:
                    logger.warning(
                        f"FFmpeg процесс завершился неожиданно (код: {process.returncode})"
                    )
                    break

                if progress_callback and frame_idx % 5 == 0:
                    percent = int((frame_idx / total_frames) * 100)
                    progress_callback.emit(percent)

                target_time = frame_idx / fps
                snap = recording.evaluate_at(target_time)

                frame_pil = self.render_snapshot_to_pil(
                    snap,
                    out_w,
                    out_h,
                    font_path,
                    should_crop,
                    fit_content,
                    global_bounds,
                    fill_rgba,
                )

                if frame_pil:
                    if frame_pil.size != (out_w, out_h):
                        frame_pil = frame_pil.resize(
                            (out_w, out_h), Image.Resampling.BILINEAR
                        )

                    try:
                        process.stdin.write(frame_pil.tobytes())
                    except (BrokenPipeError, OSError) as e:
                        logger.error(f"Ошибка записи в stdin процесса ffmpeg: {e}")
                        break

            if progress_callback and not self._cancel_requested:
                progress_callback.emit(100)

        except Exception as e:
            logger.error(f"Error during video rendering loop: {e}")
        finally:

            try:
                if process in self._active_processes:
                    self._active_processes.remove(process)
            except Exception:
                pass

            try:
                if process.stdin:
                    process.stdin.close()
            except Exception:
                pass

            stdout_output = b""
            stderr_output_raw = b""
            try:
                stdout_output, stderr_output_raw = process.communicate(timeout=30.0)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg процесс все еще работает, пробуем завершить...")
                try:
                    process.terminate()
                    stdout_output, stderr_output_raw = process.communicate(timeout=5.0)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg не завершился, принудительно убиваем...")
                    process.kill()
                    stdout_output, stderr_output_raw = process.communicate()
                except Exception as e:
                    logger.error(f"Ошибка при завершении процесса ffmpeg: {e}")
                    try:
                        process.kill()
                    except Exception:
                        pass
                    try:
                        stdout_output, stderr_output_raw = process.communicate()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Ошибка при ожидании завершения ffmpeg: {e}")
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    stdout_output, stderr_output_raw = process.communicate()
                except Exception:
                    pass

            try:
                stderr_output = (
                    stderr_output_raw.decode("utf-8", errors="ignore")
                    if stderr_output_raw
                    else ""
                )
            except Exception:
                stderr_output = ""

        if self._cancel_requested or export_canceled:
            self.images_cache.clear()
            return None

        if process.returncode != 0:
            logger.error(f"FFmpeg exited with error code {process.returncode}")
            if stderr_output:
                logger.error(f"FFmpeg log: {stderr_output}")
            self.images_cache.clear()
            return None

        logger.info(f"Video export successful: {video_path}")

        self.images_cache.clear()
        return video_path

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
