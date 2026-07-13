from enum import StrEnum

class AppConstants:
    DISPLAY_RESOLUTION_OPTIONS = {
        "Original": 0,
        "8K (4320p)": 4320,
        "4K (2160p)": 2160,
        "2K (1440p)": 1440,
        "Full HD (1080p)": 1080,
    }
    DEFAULT_DISPLAY_RESOLUTION_LIMIT = 2160

    MIN_NAME_LENGTH_LIMIT = 10
    MAX_NAME_LENGTH_LIMIT = 150
    DEFAULT_JPEG_QUALITY = 93
    DEFAULT_INTERPOLATION_METHOD = "LANCZOS"
    BASE_MOVEMENT_SPEED = 0.5
    MIN_CHANGE_THRESHOLD = 0.0001
    SMOOTHING_FACTOR_POS = 0.15
    SMOOTHING_FACTOR_SPACING = 0.2
    SMOOTHING_FACTOR_SPLIT = 0.2
    LERP_STOP_THRESHOLD = 0.001
    MAX_TARGET_DELTA_PER_TICK = 0.1

    INTERPOLATION_METHODS_MAP = {
        "NEAREST": "Nearest Neighbor",
        "BILINEAR": "Bilinear",
        "BICUBIC": "Bicubic",
        "LANCZOS": "Lanczos",
        "EWA_LANCZOS": "EWA Lanczos",
    }

    INTERPOLATION_SPEED_ORDER = {
        "NEAREST": 0,
        "BILINEAR": 1,
        "BICUBIC": 2,
        "LANCZOS": 3,
        "EWA_LANCZOS": 4,
    }

    @staticmethod
    def is_interpolation_conflict(main_method: str, optimization_method: str) -> bool:
        main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_method, 999)
        opt_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(optimization_method, 999)
        return main_speed <= opt_speed

    FLYOUT_ANIMATION_DURATION_MS = 150
    TEXT_SETTINGS_FLYOUT_ANIMATION_DURATION_MS = 150
    TRANSIENT_HOVER_OPEN_DELAY_MS = 150
    TRANSIENT_AUTO_HIDE_DELAY_MS = 300
    TRANSIENT_WHEEL_AUTO_HIDE_DELAY_MS = 1200
    TRANSIENT_FLYOUT_SHOW_DELAY_MS = 250
    TRANSIENT_FLYOUT_HIDE_CHECK_DELAY_MS = 300

    PROGRESSIVE_LOAD_THRESHOLD_BYTES = 2 * 1024 * 1024
    PROGRESSIVE_LOAD_THRESHOLD_PIXELS = 1920 * 1080
    # docs/dev/TILED_RENDERING_DESIGN.md Phase 1: the live canvas now tiles
    # images bigger than one GPU texture (TileTextureService), so this is no
    # longer a "single texture" ceiling — it is a sanity bound against
    # pathological/corrupt files, decoded fully into memory once (RGBA8:
    # ~2.7GB at this ceiling). Raise further only alongside a real streaming
    # decode path (design doc "Provider callback cost" open question).
    MAX_SUPPORTED_IMAGE_DIMENSION = 32768
    # docs/dev/rendering/tile-rendering-system.md Phase 3: past this size per
    # side, the decoded full-res image is spilled to a memmap-backed
    # LazyPixelSource instead of staying resident as a Python-owned PIL
    # buffer for the document's lifetime. 2x the live tile extent (8192,
    # see rhi_renderer/resources.py's _LIVE_TILE_EXTENT) -- large enough
    # that ordinary images never engage this path, matching the doc's own
    # suggested threshold.
    PHASE3_LAZY_THRESHOLD_PX = 16384

class Events(StrEnum):

    CORE_UPDATE_REQUESTED = "core.update_requested"
    CORE_ERROR_OCCURRED = "core.error_occurred"

    EXPORT_TOGGLE_RECORDING = "export.toggle_recording"
    EXPORT_TOGGLE_PAUSE_RECORDING = "export.toggle_pause_recording"
    EXPORT_OPEN_VIDEO_EDITOR = "export.open_video_editor"
    EXPORT_PASTE_IMAGE_FROM_CLIPBOARD = "export.paste_image_from_clipboard"

    ANALYSIS_SET_CHANNEL_VIEW_MODE = "analysis.set_channel_view_mode"
    ANALYSIS_TOGGLE_DIFF_MODE = "analysis.toggle_diff_mode"
    ANALYSIS_SET_DIFF_MODE = "analysis.set_diff_mode"
    ANALYSIS_METRICS_UPDATED = "analysis.metrics_updated"
    ANALYSIS_REQUEST_METRICS = "analysis.request_metrics"

    SETTINGS_CHANGE_LANGUAGE = "settings.change_language"
    SETTINGS_TOGGLE_INCLUDE_FILENAMES_IN_SAVED = (
        "settings.toggle_include_filenames_in_saved"
    )
    SETTINGS_APPLY_FONT_SETTINGS = "settings.apply_font_settings"
    SETTINGS_TOGGLE_AUTO_CROP_BLACK_BORDERS = "settings.toggle_auto_crop_black_borders"
    SETTINGS_UI_MODE_CHANGED = "settings.ui_mode_changed"

    COMPARISON_UI_UPDATE = "comparison.ui_update"
    COMPARISON_ERROR = "comparison.error"
    COMPARISON_UPDATE_REQUESTED = "comparison.update_requested"

    @staticmethod
    def plugin_event(plugin_name: str, stage: str) -> str:
        return f"plugin.{plugin_name}.{stage}"
