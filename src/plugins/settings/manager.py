import logging
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtGui import QColor
from core.store import Store
from core.constants import AppConstants

logger = logging.getLogger("ImproveImgSLI")

class SettingsManager:
    def __init__(self, organization_name, application_name):
        self.settings = QSettings(organization_name, application_name)

    def _get_setting(self, key, default, target_type):
        if not self.settings.contains(key): return default
        val = self.settings.value(key)
        try:
            if target_type == QPointF:
                if isinstance(val, QPointF): return val
                x, y = map(float, str(val).split(","))
                return QPointF(x, y)
            if target_type == bool: return str(val).lower() == "true"
            if target_type == int: return int(float(val))
            if target_type == float: return float(val)
            return target_type(val)
        except: return default

    def load_all_settings(self, store: Store):
        v, s = store.viewport, store.settings
        v.max_name_length = self._get_setting("max_name_length", 50, int)
        v.display_resolution_limit = self._get_setting("display_resolution_limit", 2160, int)

        v.magnifier_size_relative = self._get_setting("magnifier_size_relative", 0.4, float)
        v.capture_size_relative = self._get_setting("capture_size_relative", 0.1, float)
        v.movement_speed_per_sec = self._get_setting("movement_speed_per_sec", 2.0, float)

        v.capture_position_relative = AppConstants.DEFAULT_CAPTURE_POS_RELATIVE
        v.magnifier_offset_relative = AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        v.magnifier_offset_relative_visual = v.magnifier_offset_relative

        s.theme = self._get_setting("theme", "auto", str)
        s.current_language = self._get_setting("language", "en", str)
        s.ui_mode = self._get_setting("ui_mode", "beginner", str)
        s.system_notifications_enabled = self._get_setting("system_notifications_enabled", True, bool)
        s.auto_crop_black_borders = self._get_setting("auto_crop_black_borders", True, bool)
        s.video_recording_fps = self._get_setting("video_recording_fps", 60, int)

        v.divider_line_thickness = self._get_setting("divider_line_thickness", 3, int)
        v.divider_line_color = QColor(self._get_setting("divider_line_color", "#FFFFFFFF", str))
        v.divider_line_visible = self._get_setting("divider_line_visible", True, bool)

        v.magnifier_divider_thickness = self._get_setting("magnifier_divider_thickness", 2, int)
        v.magnifier_divider_color = QColor(self._get_setting("magnifier_divider_color", "#E6FFFFFF", str))
        v.magnifier_divider_visible = self._get_setting("magnifier_divider_visible", True, bool)

        v.magnifier_guides_thickness = self._get_setting("magnifier_guides_thickness", 1, int)

        v.font_size_percent = self._get_setting("font_size_percent", 100, int)
        v.font_weight = self._get_setting("font_weight", 0, int)
        v.text_alpha_percent = self._get_setting("text_alpha_percent", 100, int)
        v.file_name_color = QColor(self._get_setting("filename_color", "#FFFF0000", str))
        v.file_name_bg_color = QColor(self._get_setting("filename_bg_color", "#50000000", str))
        v.draw_text_background = self._get_setting("draw_text_background", True, bool)
        v.text_placement_mode = self._get_setting("text_placement_mode", "edges", str)
        v.include_file_names_in_saved = self._get_setting("include_file_names_in_saved", False, bool)

        v.optimize_laser_smoothing = self._get_setting("optimize_laser_smoothing", False, bool)

        magnifier_movement_interp = self._get_setting("magnifier_movement_interpolation_method", None, str)
        laser_smoothing_interp = self._get_setting("laser_smoothing_interpolation_method", None, str)

        if magnifier_movement_interp is None:
            movement_interp = self._get_setting("movement_interpolation_method", "BILINEAR", str)
            magnifier_movement_interp = movement_interp
            laser_smoothing_interp = movement_interp

        v.render_config.magnifier_movement_interpolation_method = magnifier_movement_interp
        v.render_config.laser_smoothing_interpolation_method = laser_smoothing_interp or "BILINEAR"

        v.render_config.movement_interpolation_method = magnifier_movement_interp
        v.movement_interpolation_method = magnifier_movement_interp

        s.window_width = self._get_setting("window_width", 1024, int)
        s.window_height = self._get_setting("window_height", 768, int)
        s.window_x = self._get_setting("window_x", 100, int)
        s.window_y = self._get_setting("window_y", 100, int)
        s.window_was_maximized = self._get_setting("window_was_maximized", False, bool)

        s.export_favorite_dir = self._get_setting("export_favorite_dir", None, str)
        s.export_video_favorite_dir = self._get_setting("export_video_favorite_dir", None, str)

    def save_all_settings(self, store: Store):
        v, s = store.viewport, store.settings
        self._save_setting("max_name_length", v.max_name_length)
        self._save_setting("display_resolution_limit", v.display_resolution_limit)

        self._save_setting("magnifier_size_relative", v.magnifier_size_relative)
        self._save_setting("capture_size_relative", v.capture_size_relative)
        self._save_setting("movement_speed_per_sec", v.movement_speed_per_sec)

        self._save_setting("theme", s.theme)
        self._save_setting("language", s.current_language)
        self._save_setting("ui_mode", s.ui_mode)
        self._save_setting("system_notifications_enabled", s.system_notifications_enabled)
        self._save_setting("auto_crop_black_borders", s.auto_crop_black_borders)
        self._save_setting("video_recording_fps", s.video_recording_fps)

        self._save_setting("divider_line_thickness", v.divider_line_thickness)
        self._save_setting("divider_line_color", v.divider_line_color.name(QColor.NameFormat.HexArgb))
        self._save_setting("divider_line_visible", v.divider_line_visible)

        self._save_setting("magnifier_divider_thickness", v.magnifier_divider_thickness)
        self._save_setting("magnifier_divider_color", v.magnifier_divider_color.name(QColor.NameFormat.HexArgb))
        self._save_setting("magnifier_divider_visible", v.magnifier_divider_visible)

        self._save_setting("magnifier_guides_thickness", v.magnifier_guides_thickness)

        self._save_setting("font_size_percent", v.font_size_percent)
        self._save_setting("font_weight", v.font_weight)
        self._save_setting("text_alpha_percent", v.text_alpha_percent)
        self._save_setting("filename_color", v.file_name_color)
        self._save_setting("filename_bg_color", v.file_name_bg_color)
        self._save_setting("draw_text_background", v.draw_text_background)
        self._save_setting("text_placement_mode", v.text_placement_mode)
        self._save_setting("include_file_names_in_saved", v.include_file_names_in_saved)

        self._save_setting("optimize_laser_smoothing", v.optimize_laser_smoothing)

        self._save_setting("magnifier_movement_interpolation_method", v.render_config.magnifier_movement_interpolation_method)
        self._save_setting("laser_smoothing_interpolation_method", v.render_config.laser_smoothing_interpolation_method)

        self._save_setting("movement_interpolation_method", v.movement_interpolation_method)

        self._save_setting("window_width", s.window_width)
        self._save_setting("window_height", s.window_height)
        self._save_setting("window_x", s.window_x)
        self._save_setting("window_y", s.window_y)
        self._save_setting("window_was_maximized", s.window_was_maximized)

        self.settings.sync()

    def _save_setting(self, key, value):
        if value is None: return
        if isinstance(value, QPointF):
            self.settings.setValue(key, f"{value.x()},{value.y()}")
        elif isinstance(value, QColor):
            self.settings.setValue(key, value.name(QColor.NameFormat.HexArgb))
        else:
            self.settings.setValue(key, value)

    def is_first_run(self) -> bool:
        return self._get_setting("is_first_run", True, bool)

    def set_first_run_completed(self):
        self._save_setting("is_first_run", False)

