from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import threading

from tabs.image_compare.plugins.video_editor.services.export_config import ExportConfigBuilder

logger = logging.getLogger("ImproveImgSLI")

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
            "-progress",
            "pipe:2",
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
                ["-c:v", "prores_ks", "-profile:v", profile_map.get(preset, "2"), "-pix_fmt", pix_fmt]
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
                    ["-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", "-c:v", "gif"]
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
                            if key == "progress":
                                if progress_block:
                                    _emit_progress_block(progress_block)
                                    progress_block = {}
                            else:
                                progress_block[key] = value
                        else:
                            self._stderr_lines.append(line)
                            if stderr_line_callback:
                                try:
                                    stderr_line_callback(line)
                                except Exception:
                                    pass
            except Exception as exc:
                logger.debug("FFmpegProcessManager: stderr drain exception: %s", exc, exc_info=True)

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

        logger.info("Завершение %s активных процессов ffmpeg...", len(self._active_processes))
        for process in self._active_processes[:]:
            if process.poll() is None:
                try:
                    logger.debug("Завершение процесса ffmpeg (PID: %s)...", process.pid)
                    process.terminate()
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Процесс ffmpeg (PID: %s) не завершился, принудительно убиваем...",
                        process.pid,
                    )
                    process.kill()
                    process.wait()
                except Exception as exc:
                    logger.error(
                        "Ошибка при завершении процесса ffmpeg (PID: %s): %s",
                        process.pid,
                        exc,
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
            except Exception as exc:
                logger.error("Ошибка при завершении процесса ffmpeg: %s", exc)
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
        except Exception as exc:
            logger.error("Ошибка при ожидании завершения ffmpeg: %s", exc)
            try:
                process.kill()
                process.wait()
            except Exception:
                pass
