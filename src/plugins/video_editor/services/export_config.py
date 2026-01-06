import logging
from typing import Dict, List, Any

logger = logging.getLogger("ImproveImgSLI")

EXPORT_FORMATS = {
    "mp4": {
        "codecs": ["h264 (AVC)", "h265 (HEVC)", "av1", "vp9"],
        "default_codec": "h264 (AVC)"
    },
    "mkv": {
        "codecs": ["h264 (AVC)", "h265 (HEVC)", "vp9", "av1", "prores", "raw"],
        "default_codec": "h264 (AVC)"
    },
    "webm": {
        "codecs": ["vp9", "av1"],
        "default_codec": "vp9"
    },
    "mov": {
        "codecs": ["prores", "h264 (AVC)"],
        "default_codec": "prores"
    },
    "gif": {
        "codecs": ["gif"],
        "default_codec": "gif"
    },
    "avi": {
        "codecs": ["h264 (AVC)", "raw"],
        "default_codec": "h264 (AVC)"
    }
}

CODEC_MAPPING = {
    "h264 (AVC)": "h264",
    "h265 (HEVC)": "h265",
    "av1": "av1",
    "vp9": "vp9",
    "prores": "prores",
    "gif": "gif",
    "raw": "raw"
}

ENCODING_PRESETS_STANDARD = [
    "ultrafast", "superfast", "veryfast", "faster",
    "fast", "medium", "slow", "slower", "veryslow"
]

PRESETS_PRORES = [
    "proxy", "lt", "standard", "hq", "4444"
]

PRESETS_GIF = [
    "High Quality", "Balanced", "Compact (Dithered)"
]

DEFAULT_CRF_VALUES = {
    "h264": 23,
    "h265": 26,
    "vp9": 31,
    "av1": 31,
    "prores": 0,
    "gif": 0,
    "raw": 0
}

class ExportConfigBuilder:

    @staticmethod
    def get_available_containers() -> List[str]:
        return list(EXPORT_FORMATS.keys())

    @staticmethod
    def get_codecs_for_container(container: str) -> List[str]:
        if container in EXPORT_FORMATS:
            return EXPORT_FORMATS[container]["codecs"]
        return ["h264 (AVC)"]

    @staticmethod
    def get_default_codec_for_container(container: str) -> str:
        if container in EXPORT_FORMATS:
            return EXPORT_FORMATS[container]["default_codec"]
        return "h264 (AVC)"

    @staticmethod
    def get_encoding_presets() -> List[str]:
        return ENCODING_PRESETS_STANDARD

    @staticmethod
    def get_codec_internal_name(codec_display_name: str) -> str:
        return CODEC_MAPPING.get(codec_display_name, "h264")

    @staticmethod
    def get_presets_for_codec(codec_display_name: str) -> List[str]:
        internal = ExportConfigBuilder.get_codec_internal_name(codec_display_name)

        if internal == "prores":
            return PRESETS_PRORES
        elif internal == "gif":
            return PRESETS_GIF
        elif internal == "raw":
            return []

        return ENCODING_PRESETS_STANDARD

    @staticmethod
    def get_codec_capabilities(codec_display_name: str) -> Dict[str, Any]:
        internal = ExportConfigBuilder.get_codec_internal_name(codec_display_name)

        caps = {
            "has_crf": True,
            "has_bitrate": True,
            "has_preset": True,
            "preset_label": "video.encoding_speed_preset"
        }

        if internal == "gif":
            caps["has_crf"] = False
            caps["has_bitrate"] = False
            caps["preset_label"] = "video.qualitysize_preset"

        elif internal == "prores":
            caps["has_crf"] = False
            caps["has_bitrate"] = False
            caps["preset_label"] = "video.prores_profile"

        elif internal == "raw":
            caps["has_crf"] = False
            caps["has_bitrate"] = False
            caps["has_preset"] = False

        return caps

    @staticmethod
    def get_default_crf_for_codec(codec_name: str) -> int:
        internal_codec = CODEC_MAPPING.get(codec_name, "h264")
        return DEFAULT_CRF_VALUES.get(internal_codec, 23)

    @staticmethod
    def build_export_config(
        container: str,
        codec: str,
        quality_mode: str = "crf",
        crf: int = 23,
        bitrate: str = "8000k",
        preset: str = "medium",
        manual_mode: bool = False,
        manual_args: str = ""
    ) -> Dict[str, Any]:
        """
        Собирает конфигурацию экспорта из параметров.
        """
        config = {
            "container": container,
            "codec": codec,
            "quality_mode": quality_mode,
            "crf": crf,
            "bitrate": bitrate,
            "preset": preset,
            "manual_mode": manual_mode,
            "manual_args": manual_args
        }

        config = ExportConfigBuilder.validate_and_fix_config(config)

        return config

    @staticmethod
    def validate_and_fix_config(config: Dict[str, Any]) -> Dict[str, Any]:
        result = config.copy()

        if result.get("container") not in EXPORT_FORMATS:
            result["container"] = "mp4"
            logger.warning(f"Invalid container, using default: mp4")

        valid_codecs = ExportConfigBuilder.get_codecs_for_container(result["container"])
        if result.get("codec") not in valid_codecs:
            result["codec"] = ExportConfigBuilder.get_default_codec_for_container(result["container"])
            logger.warning(f"Invalid codec for container {result['container']}, using default: {result['codec']}")

        internal_codec = ExportConfigBuilder.get_codec_internal_name(result["codec"])

        if internal_codec == "gif":
            if result.get("preset") not in PRESETS_GIF:
                result["preset"] = PRESETS_GIF[0]
        elif internal_codec == "prores":
            if result.get("preset") not in PRESETS_PRORES:
                result["preset"] = "standard"
        elif internal_codec == "raw":
            result["preset"] = ""
        else:
            if result.get("preset") not in ENCODING_PRESETS_STANDARD:
                result["preset"] = "medium"

        if result.get("quality_mode") not in ["crf", "bitrate"]:
            result["quality_mode"] = "crf"

        try:
            crf = int(result.get("crf", 23))
            if crf < 0 or crf > 63:
                crf = 23
            result["crf"] = crf
        except (ValueError, TypeError):
            result["crf"] = 23
            logger.warning("Invalid CRF value, using default: 23")

        bitrate = result.get("bitrate", "8000k")
        if not isinstance(bitrate, str) or not bitrate:
            result["bitrate"] = "8000k"

        if not isinstance(result.get("manual_mode"), bool):
            result["manual_mode"] = False

        if not isinstance(result.get("manual_args"), str):
            result["manual_args"] = ""

        return result

    @staticmethod
    def map_codec_to_internal_name(codec_display_name: str) -> str:
        return CODEC_MAPPING.get(codec_display_name, "h264")

