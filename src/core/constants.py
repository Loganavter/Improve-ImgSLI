from enum import StrEnum
from PyQt6.QtCore import QPointF

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
    DEFAULT_MAGNIFIER_SIZE_RELATIVE = 0.4
    DEFAULT_CAPTURE_SIZE_RELATIVE = 0.1
    DEFAULT_CAPTURE_POS_RELATIVE = QPointF(0.5, 0.5)
    DEFAULT_MAGNIFIER_OFFSET_RELATIVE = QPointF(0.0, -0.15)
    DEFAULT_MAGNIFIER_SPACING_RELATIVE = 0.1

    MIN_MAGNIFIER_SPACING_RELATIVE = 0.0
    MAX_MAGNIFIER_SPACING_RELATIVE = 0.5

    MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE = 0.02

    DEFAULT_JPEG_QUALITY = 93
    DEFAULT_INTERPOLATION_METHOD = "LANCZOS"
    BASE_MOVEMENT_SPEED = 0.5
    CAPTURE_THICKNESS_FACTOR = 0.35

    MIN_CHANGE_THRESHOLD = 0.0001
    SMOOTHING_FACTOR_POS = 0.15
    SMOOTHING_FACTOR_SPACING = 0.2
    SMOOTHING_FACTOR_SPLIT = 0.2
    LERP_STOP_THRESHOLD = 0.001
    MAX_TARGET_DELTA_PER_TICK = 0.1

    MIN_CAPTURE_THICKNESS = 1
    MAX_CAPTURE_THICKNESS = 4
    MIN_MAG_BORDER_THICKNESS = 1
    MAX_MAG_BORDER_THICKNESS = 4
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

    PROGRESSIVE_LOAD_THRESHOLD_BYTES = 2 * 1024 * 1024
    PROGRESSIVE_LOAD_THRESHOLD_PIXELS = 1920 * 1080

class Events(StrEnum):

    CORE_UPDATE_REQUESTED = "core.update_requested"
    CORE_ERROR_OCCURRED = "core.error_occurred"

    VIEWPORT_SET_SPLIT_POSITION = "viewport.set_split_position"
    VIEWPORT_UPDATE_MAGNIFIER_SIZE_RELATIVE = "viewport.update_magnifier_size_relative"
    VIEWPORT_UPDATE_CAPTURE_SIZE_RELATIVE = "viewport.update_capture_size_relative"
    VIEWPORT_UPDATE_MOVEMENT_SPEED = "viewport.update_movement_speed"
    VIEWPORT_SET_MAGNIFIER_POSITION = "viewport.set_magnifier_position"
    VIEWPORT_SET_MAGNIFIER_INTERNAL_SPLIT = "viewport.set_magnifier_internal_split"
    VIEWPORT_TOGGLE_MAGNIFIER_PART = "viewport.toggle_magnifier_part"
    VIEWPORT_UPDATE_MAGNIFIER_COMBINED_STATE = "viewport.update_magnifier_combined_state"
    VIEWPORT_TOGGLE_ORIENTATION = "viewport.toggle_orientation"
    VIEWPORT_TOGGLE_MAGNIFIER_ORIENTATION = "viewport.toggle_magnifier_orientation"
    VIEWPORT_TOGGLE_FREEZE_MAGNIFIER = "viewport.toggle_freeze_magnifier"
    VIEWPORT_ON_SLIDER_PRESSED = "viewport.on_slider_pressed"
    VIEWPORT_ON_SLIDER_RELEASED = "viewport.on_slider_released"
    VIEWPORT_SET_MAGNIFIER_VISIBILITY = "viewport.set_magnifier_visibility"
    VIEWPORT_TOGGLE_MAGNIFIER = "viewport.toggle_magnifier"

    EXPORT_TOGGLE_RECORDING = "export.toggle_recording"
    EXPORT_TOGGLE_PAUSE_RECORDING = "export.toggle_pause_recording"
    EXPORT_EXPORT_RECORDED_VIDEO = "export.export_recorded_video"
    EXPORT_OPEN_VIDEO_EDITOR = "export.open_video_editor"
    EXPORT_PASTE_IMAGE_FROM_CLIPBOARD = "export.paste_image_from_clipboard"
    EXPORT_QUICK_SAVE_COMPARISON = "export.quick_save_comparison"

    ANALYSIS_SET_CHANNEL_VIEW_MODE = "analysis.set_channel_view_mode"
    ANALYSIS_TOGGLE_DIFF_MODE = "analysis.toggle_diff_mode"
    ANALYSIS_SET_DIFF_MODE = "analysis.set_diff_mode"
    ANALYSIS_METRICS_UPDATED = "analysis.metrics_updated"
    ANALYSIS_REQUEST_METRICS = "analysis.request_metrics"

    SETTINGS_CHANGE_LANGUAGE = "settings.change_language"
    SETTINGS_TOGGLE_INCLUDE_FILENAMES_IN_SAVED = "settings.toggle_include_filenames_in_saved"
    SETTINGS_APPLY_FONT_SETTINGS = "settings.apply_font_settings"
    SETTINGS_TOGGLE_DIVIDER_LINE_VISIBILITY = "settings.toggle_divider_line_visibility"
    SETTINGS_SET_DIVIDER_LINE_COLOR = "settings.set_divider_line_color"
    SETTINGS_TOGGLE_MAGNIFIER_DIVIDER_VISIBILITY = "settings.toggle_magnifier_divider_visibility"
    SETTINGS_SET_MAGNIFIER_DIVIDER_COLOR = "settings.set_magnifier_divider_color"
    SETTINGS_TOGGLE_AUTO_CROP_BLACK_BORDERS = "settings.toggle_auto_crop_black_borders"
    SETTINGS_SET_DIVIDER_LINE_THICKNESS = "settings.set_divider_line_thickness"
    SETTINGS_SET_MAGNIFIER_DIVIDER_THICKNESS = "settings.set_magnifier_divider_thickness"
    SETTINGS_UI_MODE_CHANGED = "settings.ui_mode_changed"

    COMPARISON_UI_UPDATE = "comparison.ui_update"
    COMPARISON_ERROR = "comparison.error"
    COMPARISON_UPDATE_REQUESTED = "comparison.update_requested"

    MAGNIFIER_ADDED = "magnifier.added"
    MAGNIFIER_REMOVED = "magnifier.removed"

    @staticmethod
    def plugin_event(plugin_name: str, stage: str) -> str:
        return f"plugin.{plugin_name}.{stage}"

