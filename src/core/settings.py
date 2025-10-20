import logging

from PyQt6.QtCore import QLocale, QPointF, QSettings
from PyQt6.QtGui import QColor

from core.app_state import AppState
from core.constants import AppConstants

logger = logging.getLogger("ImproveImgSLI")

class SettingsManager:
    def __init__(self, organization_name: str, application_name: str):
        self.settings = QSettings(organization_name, application_name)

    def _get_setting(self, key: str, default, target_type):
        try:
            if not self.settings.contains(key):
                return default

            value = self.settings.value(key)

            if target_type == QPointF:
                if isinstance(value, str):
                    try:
                        x_str, y_str = value.split(",")
                        return QPointF(float(x_str), float(y_str))
                    except Exception:
                        return default
                else:
                    return default
            elif target_type == QColor:
                if isinstance(value, str):
                    result = QColor(value)
                    return result if result.isValid() else default
                else:
                    return default
            elif target_type == list:
                return value if isinstance(value, list) else default
            elif target_type == bool:
                return value == "true" or value == True if value is not None else default
            else:
                try:
                    return target_type(value)
                except (ValueError, TypeError):
                    return default
        except Exception:
            return default

    def load_all_settings(self, app_state: AppState):

        app_state.loaded_debug_mode_enabled = self._get_setting(
            "debug_mode_enabled", False, bool
        )
        app_state.debug_mode_enabled = app_state.loaded_debug_mode_enabled

        app_state.system_notifications_enabled = self._get_setting(
            "system_notifications_enabled", True, bool
        )
        app_state.auto_calculate_psnr = self._get_setting(
            "auto_calculate_psnr", False, bool
        )
        app_state.auto_calculate_ssim = self._get_setting(
            "auto_calculate_ssim", False, bool
        )

        app_state.display_resolution_limit = self._get_setting(
            "display_resolution_limit",
            AppConstants.DEFAULT_DISPLAY_RESOLUTION_LIMIT,
            int,
        )
        app_state.optimize_magnifier_movement = self._get_setting(
            "optimize_magnifier_movement", True, bool
        )
        app_state.movement_interpolation_method = self._get_setting(
            "movement_interpolation_method", "BILINEAR", str
        )
        app_state.theme = self._get_setting("theme", "auto", str)

        saved_lang = self._get_setting("language", None, str)
        valid_languages = ["en", "ru", "zh", "pt_BR"]
        default_lang = QLocale.system().name().split("_")[0]
        if default_lang not in valid_languages:
            default_lang = "en"
        app_state.current_language = (
            saved_lang if saved_lang in valid_languages else default_lang
        )

        app_state.max_name_length = max(
            AppConstants.MIN_NAME_LENGTH_LIMIT,
            min(
                AppConstants.MAX_NAME_LENGTH_LIMIT,
                self._get_setting("max_name_length", 100, int),
            ),
        )
        app_state.movement_speed_per_sec = max(
            0.1, min(5.0, self._get_setting("movement_speed_per_sec", 2.0, float))
        )
        default_color = QColor(255, 0, 0, 255)
        loaded_color_name = self._get_setting(
            "filename_color", default_color.name(QColor.NameFormat.HexArgb), str
        )
        app_state.file_name_color = QColor(loaded_color_name)
        if not app_state.file_name_color.isValid():
            app_state.file_name_color = default_color

        default_bg_color = QColor(0, 0, 0, 128)
        loaded_bg_color_name = self._get_setting(
            "filename_bg_color", default_bg_color.name(QColor.NameFormat.HexArgb), str
        )
        app_state.file_name_bg_color = QColor(loaded_bg_color_name)
        if not app_state.file_name_bg_color.isValid():
            app_state.file_name_bg_color = default_bg_color

        try:
            loaded_alpha = self._get_setting("text_alpha_percent", 100, int)
            app_state.text_alpha_percent = max(0, min(100, loaded_alpha))
        except Exception:
            app_state.text_alpha_percent = 100

        app_state.jpeg_quality = max(
            1, min(100, self._get_setting("jpeg_quality", AppConstants.DEFAULT_JPEG_QUALITY, int))
        )
        app_state.font_weight = self._get_setting("font_weight", 0, int)
        app_state.font_size_percent = self._get_setting("font_size_percent", 100, int)
        app_state.draw_text_background = self._get_setting("draw_text_background", True, bool)
        app_state.text_placement_mode = self._get_setting("text_placement_mode", "edges", str)
        loaded_mode = self._get_setting("ui_font_mode", "builtin", str)

        if not self.settings.contains("ui_font_mode"):
            app_state.ui_font_mode = "system_default"
            app_state.ui_font_family = ""
            logger.info("First run detected: setting UI font to system default.")
        else:
            loaded_mode = self._get_setting("ui_font_mode", "builtin", str)

            if loaded_mode == "system":
                loaded_mode = "system_default"

            app_state.ui_font_mode = loaded_mode
            app_state.ui_font_family = self._get_setting("ui_font_family", "", str)
            try:
                logger.debug(f"SettingsManager.load_all_settings: ui_font_mode={app_state.ui_font_mode}, ui_font_family='{app_state.ui_font_family}'")
            except Exception:
                pass
        app_state.ui_font_mode = loaded_mode
        app_state.ui_font_family = self._get_setting("ui_font_family", "", str)
        try:
            logger.debug(f"SettingsManager.load_all_settings: ui_font_mode={app_state.ui_font_mode}, ui_font_family='{app_state.ui_font_family}'")
        except Exception:
            pass
        app_state.magnifier_offset_relative = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        app_state.magnifier_offset_relative_visual = QPointF(AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)

        default_spacing = AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE
        half_spacing = default_spacing / 2.0
        app_state.magnifier_left_offset_relative = QPointF(-half_spacing, 0.0)
        app_state.magnifier_right_offset_relative = QPointF(half_spacing, 0.0)
        app_state.magnifier_left_offset_relative_visual = QPointF(-half_spacing, 0.0)
        app_state.magnifier_right_offset_relative_visual = QPointF(half_spacing, 0.0)

        app_state.export_use_default_dir = self._get_setting("export_use_default_dir", True, bool)
        app_state.export_default_dir = self._get_setting("export_default_dir", None, str)
        app_state.export_favorite_dir = self._get_setting("export_favorite_dir", None, str)
        app_state.export_last_format = self._get_setting("export_last_format", "PNG", str)
        app_state.export_quality = max(1, min(100, self._get_setting("export_quality", app_state.jpeg_quality, int)))
        loaded_bg_color_name = self._get_setting("export_background_color", QColor(255,255,255,255).name(QColor.NameFormat.HexArgb), str)
        app_state.export_background_color = QColor(loaded_bg_color_name) if QColor(loaded_bg_color_name).isValid() else QColor(255,255,255,255)
        app_state.export_fill_background = self._get_setting("export_fill_background", False, bool)
        app_state.export_last_filename = self._get_setting("export_last_filename", "", str)
        app_state.export_png_compress_level = max(0, min(9, self._get_setting("export_png_compress_level", 9, int)))

        app_state.export_comment_text = self._get_setting("export_comment_text", "", str)
        app_state.export_comment_keep_default = self._get_setting("export_comment_keep_default", False, bool)

        app_state.divider_line_visible = self._get_setting("divider_line_visible", True, bool)
        app_state.divider_line_thickness = max(1, min(20, self._get_setting("divider_line_thickness", 3, int)))

        default_divider_color = QColor(255, 255, 255, 255)
        loaded_divider_color_name = self._get_setting(
            "divider_line_color", default_divider_color.name(QColor.NameFormat.HexArgb), str
        )
        app_state.divider_line_color = QColor(loaded_divider_color_name)
        if not app_state.divider_line_color.isValid():
            app_state.divider_line_color = default_divider_color

        app_state.magnifier_divider_visible = self._get_setting("magnifier_divider_visible", True, bool)
        app_state.magnifier_divider_thickness = max(1, min(10, self._get_setting("magnifier_divider_thickness", 2, int)))

        default_mag_divider_color = QColor(255, 255, 255, 230)
        loaded_mag_divider_color_name = self._get_setting(
            "magnifier_divider_color", default_mag_divider_color.name(QColor.NameFormat.HexArgb), str
        )
        app_state.magnifier_divider_color = QColor(loaded_mag_divider_color_name)
        if not app_state.magnifier_divider_color.isValid():
            app_state.magnifier_divider_color = default_mag_divider_color
        app_state.magnifier_is_horizontal = self._get_setting("magnifier_is_horizontal", False, bool)

        app_state.magnifier_visible_left = True
        app_state.magnifier_visible_center = True
        app_state.magnifier_visible_right = True

        app_state.is_horizontal = self._get_setting("is_horizontal", False, bool)
        app_state.use_magnifier = self._get_setting("use_magnifier", False, bool)
        app_state.freeze_magnifier = self._get_setting("freeze_magnifier", False, bool)
        app_state.include_file_names_in_saved = self._get_setting("include_file_names_in_saved", False, bool)

    def save_all_settings(self, app_state: AppState):

        self._save_setting("language", app_state.current_language)
        self._save_setting(
            "display_resolution_limit", app_state.display_resolution_limit
        )
        self._save_setting(
            "optimize_magnifier_movement", app_state.optimize_magnifier_movement
        )
        self._save_setting(
            "movement_interpolation_method", app_state.movement_interpolation_method
        )
        self._save_setting("max_name_length", app_state.max_name_length)
        self._save_setting("movement_speed_per_sec", app_state.movement_speed_per_sec)
        self._save_setting(
            "filename_color", app_state.file_name_color.name(QColor.NameFormat.HexArgb)
        )
        self._save_setting(
            "filename_bg_color", app_state.file_name_bg_color.name(QColor.NameFormat.HexArgb)
        )
        self._save_setting("jpeg_quality", app_state.jpeg_quality)
        self._save_setting("font_weight", app_state.font_weight)
        self._save_setting("font_size_percent", app_state.font_size_percent)
        self._save_setting("draw_text_background", app_state.draw_text_background)
        self._save_setting(
            "text_placement_mode", app_state.text_placement_mode
        )
        self._save_setting("debug_mode_enabled", app_state.debug_mode_enabled)
        self._save_setting("auto_calculate_psnr", app_state.auto_calculate_psnr)
        self._save_setting("auto_calculate_ssim", app_state.auto_calculate_ssim)
        self._save_setting("system_notifications_enabled", getattr(app_state, "system_notifications_enabled", True))
        self._save_setting("theme", app_state.theme)
        self._save_setting("ui_font_mode", getattr(app_state, "ui_font_mode", "builtin"))
        self._save_setting("ui_font_family", getattr(app_state, "ui_font_family", ""))

        self._save_setting("export_use_default_dir", app_state.export_use_default_dir)
        if app_state.export_default_dir:
            self._save_setting("export_default_dir", app_state.export_default_dir)
        if app_state.export_favorite_dir:
            self._save_setting("export_favorite_dir", app_state.export_favorite_dir)
        self._save_setting("export_last_format", app_state.export_last_format)
        self._save_setting("export_quality", max(1, min(100, app_state.export_quality)))
        self._save_setting("export_background_color", app_state.export_background_color)
        self._save_setting("export_fill_background", app_state.export_fill_background)
        self._save_setting("export_last_filename", app_state.export_last_filename)
        self._save_setting("export_png_compress_level", max(0, min(9, getattr(app_state, "export_png_compress_level", 9))))

        self._save_setting("export_comment_text", getattr(app_state, "export_comment_text", ""))
        self._save_setting("export_comment_keep_default", getattr(app_state, "export_comment_keep_default", False))

        self._save_setting("divider_line_visible", app_state.divider_line_visible)
        self._save_setting("divider_line_thickness", app_state.divider_line_thickness)
        self._save_setting("divider_line_color", app_state.divider_line_color.name(QColor.NameFormat.HexArgb))

        self._save_setting("magnifier_divider_visible", app_state.magnifier_divider_visible)
        self._save_setting("magnifier_divider_thickness", app_state.magnifier_divider_thickness)
        self._save_setting("magnifier_divider_color", app_state.magnifier_divider_color.name(QColor.NameFormat.HexArgb))
        self._save_setting("magnifier_is_horizontal", app_state.magnifier_is_horizontal)

        self._save_setting("is_horizontal", app_state.is_horizontal)
        self._save_setting("use_magnifier", app_state.use_magnifier)
        self._save_setting("freeze_magnifier", app_state.freeze_magnifier)
        self._save_setting("include_file_names_in_saved", app_state.include_file_names_in_saved)

        self.settings.sync()

    def _save_setting(self, key: str, value):
        try:
            value_to_save = None
            if isinstance(value, QPointF):
                value_to_save = f"{value.x()},{value.y()}"
            elif isinstance(value, QColor):
                value_to_save = value.name(QColor.NameFormat.HexArgb)
            elif isinstance(value, (int, float, bool, str)):
                value_to_save = value
            elif isinstance(value, list) and all((isinstance(item, str) for item in value)):
                value_to_save = value
            else:
                return

            if value_to_save is not None:
                self.settings.setValue(key, value_to_save)
        except Exception as e:
            logger.error(f"Error saving setting '{key}' with value '{value}': {e}", exc_info=True)
