from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ImproveImgSLI")

@dataclass(frozen=True)
class CodecQualityOptions:
    has_crf: bool = False
    has_cq: bool = False
    has_bitrate: bool = True
    quality_value_label: str = "video.crf_value_hint"

@dataclass(frozen=True)
class CodecProfile:
    codec_id: str
    display_name: str
    display_key: str
    family: str
    ffmpeg_encoder: str
    hardware: bool = False
    allowed_containers: tuple[str, ...] = ()
    presets: tuple[str, ...] = ()
    pixel_formats: tuple[str, ...] = ()
    default_pixel_format: str = ""
    default_preset: str = ""
    quality: CodecQualityOptions = field(default_factory=CodecQualityOptions)

STANDARD_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)
PRORES_PRESETS = ("proxy", "lt", "standard", "hq", "4444")
GIF_PRESETS = ("High Quality", "Balanced", "Compact (Dithered)")
NVENC_PRESETS = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")
QSV_PRESETS = ("veryfast", "faster", "fast", "medium", "slow", "slower")
AMF_PRESETS = ("speed", "balanced", "quality")

PIXEL_FORMATS_BY_FAMILY = {
    "h264": ("yuv420p", "yuv422p", "yuv444p"),
    "h265": (
        "yuv420p",
        "yuv422p",
        "yuv444p",
        "yuv420p10le",
        "yuv422p10le",
        "yuv444p10le",
    ),
    "vp9": (
        "yuv420p",
        "yuv422p",
        "yuv444p",
        "yuv420p10le",
        "yuv422p10le",
        "yuv444p10le",
    ),
    "av1": (
        "yuv420p",
        "yuv422p",
        "yuv444p",
        "yuv420p10le",
        "yuv422p10le",
        "yuv444p10le",
    ),
    "prores": ("yuv422p10le", "yuv444p10le"),
    "raw": (
        "yuv420p",
        "yuv422p",
        "yuv444p",
        "yuv420p10le",
        "yuv422p10le",
        "yuv444p10le",
        "rgba",
    ),
    "gif": (),
}

DEFAULT_PIXEL_FORMAT_BY_FAMILY = {
    "h264": "yuv420p",
    "h265": "yuv420p",
    "vp9": "yuv420p",
    "av1": "yuv420p",
    "prores": "yuv422p10le",
    "raw": "yuv420p",
    "gif": "",
}

DEFAULT_CRF_BY_FAMILY = {
    "h264": 23,
    "h265": 26,
    "vp9": 31,
    "av1": 31,
    "prores": 0,
    "gif": 0,
    "raw": 0,
}

PRESET_TRANSLATION_KEYS = {
    "High Quality": "video.high_quality",
    "Balanced": "video.balanced",
    "Compact (Dithered)": "video.compact_dithered",
    "ultrafast": "video.ultrafast",
    "superfast": "video.superfast",
    "veryfast": "video.veryfast",
    "faster": "video.faster",
    "fast": "video.fast",
    "medium": "video.medium",
    "slow": "video.slow",
    "slower": "video.slower",
    "veryslow": "video.veryslow",
    "proxy": "video.proxy",
    "lt": "video.lt",
    "standard": "video.standard",
    "hq": "video.hq",
    "4444": "video.4444",
    "balanced": "video.balanced",
}

CONTAINER_CODEC_IDS = {
    "mp4": (
        "h264",
        "h264_nvenc",
        "h264_qsv",
        "h264_amf",
        "h265",
        "hevc_nvenc",
        "hevc_qsv",
        "hevc_amf",
        "av1",
        "av1_nvenc",
        "av1_qsv",
        "av1_amf",
        "vp9",
    ),
    "mkv": (
        "h264",
        "h264_nvenc",
        "h264_qsv",
        "h264_amf",
        "h265",
        "hevc_nvenc",
        "hevc_qsv",
        "hevc_amf",
        "vp9",
        "av1",
        "av1_nvenc",
        "av1_qsv",
        "av1_amf",
        "prores",
        "raw",
    ),
    "webm": ("vp9", "av1", "av1_nvenc", "av1_qsv", "av1_amf"),
    "mov": ("prores", "h264", "h264_nvenc", "h264_qsv", "h264_amf"),
    "gif": ("gif",),
    "avi": ("h264", "h264_nvenc", "h264_qsv", "h264_amf", "raw"),
}

DEFAULT_CODEC_ID_BY_CONTAINER = {
    "mp4": "h264",
    "mkv": "h264",
    "webm": "vp9",
    "mov": "prores",
    "gif": "gif",
    "avi": "h264",
}

def _profile(
    codec_id: str,
    display_name: str,
    display_key: str,
    family: str,
    ffmpeg_encoder: str,
    *,
    hardware: bool = False,
    presets: tuple[str, ...] = (),
    pixel_formats: tuple[str, ...] | None = None,
    default_pixel_format: str | None = None,
    default_preset: str = "",
    quality: CodecQualityOptions | None = None,
) -> CodecProfile:
    pf = pixel_formats if pixel_formats is not None else PIXEL_FORMATS_BY_FAMILY.get(family, ("yuv420p",))
    default_pf = default_pixel_format if default_pixel_format is not None else DEFAULT_PIXEL_FORMAT_BY_FAMILY.get(family, "yuv420p")
    return CodecProfile(
        codec_id=codec_id,
        display_name=display_name,
        display_key=display_key,
        family=family,
        ffmpeg_encoder=ffmpeg_encoder,
        hardware=hardware,
        presets=presets,
        pixel_formats=pf,
        default_pixel_format=default_pf,
        default_preset=default_preset,
        quality=quality or CodecQualityOptions(
            has_crf=family not in {"prores", "gif", "raw"} and not hardware,
            has_bitrate=family not in {"prores", "gif", "raw"} or hardware,
        ),
    )

CODEC_PROFILES = {
    "h264": _profile("h264", "h264 (AVC)", "video.h264_avc", "h264", "libx264", presets=STANDARD_PRESETS, default_preset="medium"),
    "h264_nvenc": _profile(
        "h264_nvenc",
        "h264 (AVC) [NVENC]",
        "video.h264_avc_nvenc",
        "h264",
        "h264_nvenc",
        hardware=True,
        presets=NVENC_PRESETS,
        default_preset="p4",
        quality=CodecQualityOptions(has_cq=True, has_bitrate=True, quality_value_label="video.cq_value_hint"),
    ),
    "h264_qsv": _profile(
        "h264_qsv",
        "h264 (AVC) [QSV]",
        "video.h264_avc_qsv",
        "h264",
        "h264_qsv",
        hardware=True,
        presets=QSV_PRESETS,
        default_preset="medium",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "h264_amf": _profile(
        "h264_amf",
        "h264 (AVC) [AMF]",
        "video.h264_avc_amf",
        "h264",
        "h264_amf",
        hardware=True,
        presets=AMF_PRESETS,
        default_preset="balanced",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "h265": _profile("h265", "h265 (HEVC)", "video.h265_hevc", "h265", "libx265", presets=STANDARD_PRESETS, default_preset="medium"),
    "hevc_nvenc": _profile(
        "hevc_nvenc",
        "h265 (HEVC) [NVENC]",
        "video.h265_hevc_nvenc",
        "h265",
        "hevc_nvenc",
        hardware=True,
        presets=NVENC_PRESETS,
        default_preset="p4",
        quality=CodecQualityOptions(has_cq=True, has_bitrate=True, quality_value_label="video.cq_value_hint"),
    ),
    "hevc_qsv": _profile(
        "hevc_qsv",
        "h265 (HEVC) [QSV]",
        "video.h265_hevc_qsv",
        "h265",
        "hevc_qsv",
        hardware=True,
        presets=QSV_PRESETS,
        default_preset="medium",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "hevc_amf": _profile(
        "hevc_amf",
        "h265 (HEVC) [AMF]",
        "video.h265_hevc_amf",
        "h265",
        "hevc_amf",
        hardware=True,
        presets=AMF_PRESETS,
        default_preset="balanced",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "av1": _profile("av1", "av1", "video.av1", "av1", "libaom-av1", presets=STANDARD_PRESETS, default_preset="medium"),
    "av1_nvenc": _profile(
        "av1_nvenc",
        "av1 [NVENC]",
        "video.av1_nvenc",
        "av1",
        "av1_nvenc",
        hardware=True,
        presets=NVENC_PRESETS,
        default_preset="p4",
        quality=CodecQualityOptions(has_cq=True, has_bitrate=True, quality_value_label="video.cq_value_hint"),
    ),
    "av1_qsv": _profile(
        "av1_qsv",
        "av1 [QSV]",
        "video.av1_qsv",
        "av1",
        "av1_qsv",
        hardware=True,
        presets=QSV_PRESETS,
        default_preset="medium",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "av1_amf": _profile(
        "av1_amf",
        "av1 [AMF]",
        "video.av1_amf",
        "av1",
        "av1_amf",
        hardware=True,
        presets=AMF_PRESETS,
        default_preset="balanced",
        quality=CodecQualityOptions(has_bitrate=True),
    ),
    "vp9": _profile("vp9", "vp9", "video.vp9", "vp9", "libvpx-vp9", presets=STANDARD_PRESETS, default_preset="medium"),
    "prores": _profile(
        "prores",
        "prores",
        "video.prores",
        "prores",
        "prores_ks",
        presets=PRORES_PRESETS,
        default_preset="standard",
        quality=CodecQualityOptions(has_bitrate=False),
    ),
    "gif": _profile(
        "video.gif",
        "gif",
        "gif",
        "gif",
        "gif",
        presets=GIF_PRESETS,
        default_preset="High Quality",
        quality=CodecQualityOptions(has_bitrate=False),
    ),
    "raw": _profile(
        "raw",
        "raw",
        "video.raw",
        "raw",
        "rawvideo",
        presets=(),
        default_preset="",
        quality=CodecQualityOptions(has_bitrate=False),
    ),
}

DISPLAY_NAME_BY_CODEC_ID = {
    codec_id: profile.display_name for codec_id, profile in CODEC_PROFILES.items()
}
CODEC_ID_BY_DISPLAY_NAME = {
    profile.display_name: codec_id for codec_id, profile in CODEC_PROFILES.items()
}

_AVAILABLE_ENCODERS_CACHE: set[str] | None = None

def _resolve_ffmpeg_executable() -> str | None:
    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe:
        return ffmpeg_exe
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    if os.path.exists(local_ffmpeg + ".exe"):
        return local_ffmpeg + ".exe"
    return None

def _get_available_ffmpeg_encoders() -> set[str]:
    global _AVAILABLE_ENCODERS_CACHE
    if _AVAILABLE_ENCODERS_CACHE is not None:
        return _AVAILABLE_ENCODERS_CACHE
    ffmpeg_exe = _resolve_ffmpeg_executable()
    if not ffmpeg_exe:
        _AVAILABLE_ENCODERS_CACHE = set()
        return _AVAILABLE_ENCODERS_CACHE
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        encoders: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("V"):
                encoders.add(parts[1])
        _AVAILABLE_ENCODERS_CACHE = encoders
    except Exception as exc:
        logger.warning(f"Failed to detect ffmpeg encoders: {exc}")
        _AVAILABLE_ENCODERS_CACHE = set()
    return _AVAILABLE_ENCODERS_CACHE

class ExportConfigBuilder:
    @staticmethod
    def get_available_containers() -> list[str]:
        return list(CONTAINER_CODEC_IDS.keys())

    @staticmethod
    def get_profile(codec_name_or_id: str) -> CodecProfile:
        codec_id = ExportConfigBuilder.get_codec_internal_name(codec_name_or_id)
        return CODEC_PROFILES.get(codec_id, CODEC_PROFILES["h264"])

    @staticmethod
    def get_codec_internal_name(codec_display_name: str) -> str:
        if codec_display_name in CODEC_PROFILES:
            return codec_display_name
        return CODEC_ID_BY_DISPLAY_NAME.get(codec_display_name, "h264")

    @staticmethod
    def get_codec_family(codec_name_or_id: str) -> str:
        return ExportConfigBuilder.get_profile(codec_name_or_id).family

    @staticmethod
    def get_codec_display_name(codec_name_or_id: str) -> str:
        return ExportConfigBuilder.get_profile(codec_name_or_id).display_name

    @staticmethod
    def get_codec_display_key(codec_name_or_id: str) -> str:
        return ExportConfigBuilder.get_profile(codec_name_or_id).display_key

    @staticmethod
    def get_preset_translation_key(preset: str) -> str | None:
        return PRESET_TRANSLATION_KEYS.get(preset)

    @staticmethod
    def _is_codec_available(codec_id: str) -> bool:
        profile = CODEC_PROFILES.get(codec_id)
        if profile is None:
            return False
        if not profile.hardware:
            return True
        return profile.ffmpeg_encoder in _get_available_ffmpeg_encoders()

    @staticmethod
    def get_codecs_for_container(container: str) -> list[str]:
        codec_ids = CONTAINER_CODEC_IDS.get(container, ("h264",))
        return [
            CODEC_PROFILES[codec_id].display_name
            for codec_id in codec_ids
            if ExportConfigBuilder._is_codec_available(codec_id)
        ] or [CODEC_PROFILES["h264"].display_name]

    @staticmethod
    def get_codec_ids_for_container(container: str) -> list[str]:
        return [
            ExportConfigBuilder.get_codec_internal_name(codec_display)
            for codec_display in ExportConfigBuilder.get_codecs_for_container(container)
        ]

    @staticmethod
    def get_default_codec_for_container(container: str) -> str:
        default_id = DEFAULT_CODEC_ID_BY_CONTAINER.get(container, "h264")
        available_ids = ExportConfigBuilder.get_codec_ids_for_container(container)
        target_id = default_id if default_id in available_ids else (available_ids[0] if available_ids else "h264")
        return CODEC_PROFILES[target_id].display_name

    @staticmethod
    def get_default_codec_id_for_container(container: str) -> str:
        return ExportConfigBuilder.get_codec_internal_name(
            ExportConfigBuilder.get_default_codec_for_container(container)
        )

    @staticmethod
    def get_encoding_presets() -> list[str]:
        return list(STANDARD_PRESETS)

    @staticmethod
    def get_presets_for_codec(codec_name_or_id: str) -> list[str]:
        return list(ExportConfigBuilder.get_profile(codec_name_or_id).presets)

    @staticmethod
    def get_codec_capabilities(codec_name_or_id: str) -> dict[str, Any]:
        profile = ExportConfigBuilder.get_profile(codec_name_or_id)
        quality = profile.quality
        return {
            "has_crf": quality.has_crf,
            "has_cq": quality.has_cq,
            "has_bitrate": quality.has_bitrate,
            "has_preset": bool(profile.presets),
            "preset_label": (
                "video.qualitysize_preset"
                if profile.family == "gif"
                else "video.prores_profile"
                if profile.family == "prores"
                else "video.encoding_speed_preset"
            ),
            "quality_value_label": quality.quality_value_label,
        }

    @staticmethod
    def get_default_crf_for_codec(codec_name_or_id: str) -> int:
        family = ExportConfigBuilder.get_codec_family(codec_name_or_id)
        return DEFAULT_CRF_BY_FAMILY.get(family, 23)

    @staticmethod
    def get_pixel_formats_for_codec(codec_name_or_id: str) -> list[str]:
        return list(ExportConfigBuilder.get_profile(codec_name_or_id).pixel_formats)

    @staticmethod
    def get_default_pixel_format_for_codec(codec_name_or_id: str) -> str:
        return ExportConfigBuilder.get_profile(codec_name_or_id).default_pixel_format

    @staticmethod
    def build_export_config(
        container: str,
        codec: str,
        quality_mode: str = "crf",
        crf: int = 23,
        bitrate: str = "8000k",
        preset: str = "medium",
        pix_fmt: str = "yuv420p",
        manual_mode: bool = False,
        manual_args: str = "",
    ) -> dict[str, Any]:
        return ExportConfigBuilder.validate_and_fix_config(
            {
                "container": container,
                "codec": codec,
                "quality_mode": quality_mode,
                "crf": crf,
                "bitrate": bitrate,
                "preset": preset,
                "pix_fmt": pix_fmt,
                "manual_mode": manual_mode,
                "manual_args": manual_args,
            }
        )

    @staticmethod
    def validate_and_fix_config(config: dict[str, Any]) -> dict[str, Any]:
        result = dict(config)
        container = result.get("container")
        if container not in CONTAINER_CODEC_IDS:
            container = "mp4"
            result["container"] = container
            logger.warning("Invalid container, using default: mp4")

        codec_id = ExportConfigBuilder.get_codec_internal_name(str(result.get("codec") or ""))
        valid_codec_ids = ExportConfigBuilder.get_codec_ids_for_container(container)
        if codec_id not in valid_codec_ids:
            codec_id = ExportConfigBuilder.get_default_codec_id_for_container(container)
            logger.warning(
                f"Invalid codec for container {container}, using default: {ExportConfigBuilder.get_codec_display_name(codec_id)}"
            )
        result["codec"] = codec_id

        profile = ExportConfigBuilder.get_profile(codec_id)
        caps = ExportConfigBuilder.get_codec_capabilities(codec_id)

        if not isinstance(result.get("manual_mode"), bool):
            result["manual_mode"] = False
        if not isinstance(result.get("manual_args"), str):
            result["manual_args"] = ""

        presets = profile.presets
        if presets:
            if result.get("preset") not in presets:
                result["preset"] = profile.default_preset or presets[0]
        else:
            result["preset"] = ""

        allowed_quality_modes = []
        if caps["has_cq"]:
            allowed_quality_modes.append("cq")
        if caps["has_crf"]:
            allowed_quality_modes.append("crf")
        if caps["has_bitrate"]:
            allowed_quality_modes.append("bitrate")
        if result.get("quality_mode") not in allowed_quality_modes:
            result["quality_mode"] = allowed_quality_modes[0] if allowed_quality_modes else "bitrate"

        valid_pix_fmts = profile.pixel_formats
        if valid_pix_fmts:
            if result.get("pix_fmt") not in valid_pix_fmts:
                result["pix_fmt"] = profile.default_pixel_format
        else:
            result["pix_fmt"] = ""

        try:
            quality_value = int(result.get("crf", 23))
            if quality_value < 0 or quality_value > 63:
                quality_value = 23
            result["crf"] = quality_value
        except (ValueError, TypeError):
            result["crf"] = 23
            logger.warning("Invalid CRF/CQ value, using default: 23")

        bitrate = result.get("bitrate", "8000k")
        if not isinstance(bitrate, str) or not bitrate:
            result["bitrate"] = "8000k"

        return result

    @staticmethod
    def map_codec_to_internal_name(codec_display_name: str) -> str:
        return ExportConfigBuilder.get_codec_internal_name(codec_display_name)
