import logging

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

from core.constants import AppConstants
from core.store import Store
from domain.qt_adapters import hex_to_color, color_to_hex, qcolor_to_color

logger = logging.getLogger("ImproveImgSLI")

class SettingsManager:
    def __init__(self, organization_name, application_name):
        self.settings = QSettings(organization_name, application_name)

    def _get_setting(self, key, default, target_type):
        if not self.settings.contains(key):
            return default
        val = self.settings.value(key)
        try:
            if target_type == bool:
                return str(val).lower() == "true"
            if target_type == int:
                return int(float(val))
            if target_type == float:
                return float(val)
            return target_type(val)
        except:
            return default

    def load_all_settings(self, store: Store):
        v, s = store.viewport, store.settings
        render = v.render_config
        view = v.view_state

        render.max_name_length = self._get_setting("max_name_length", 50, int)
        render.display_resolution_limit = self._get_setting(
            "display_resolution_limit", 2160, int
        )

        view.magnifier_size_relative = self._get_setting(
            "magnifier_size_relative", 0.4, float
        )
        view.capture_size_relative = self._get_setting("capture_size_relative", 0.1, float)
        view.magnifier_spacing_relative = self._get_setting(
            "magnifier_spacing_relative", AppConstants.DEFAULT_MAGNIFIER_SPACING_RELATIVE, float
        )
        view.magnifier_spacing_relative_visual = view.magnifier_spacing_relative
        view.is_magnifier_combined = (
            view.magnifier_visible_left
            and view.magnifier_visible_right
            and view.magnifier_spacing_relative
            <= AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE + 1e-5
        )
        view.movement_speed_per_sec = self._get_setting(
            "movement_speed_per_sec", 2.0, float
        )

        view.capture_position_relative = AppConstants.DEFAULT_CAPTURE_POS_RELATIVE
        view.magnifier_offset_relative = AppConstants.DEFAULT_MAGNIFIER_OFFSET_RELATIVE
        view.magnifier_offset_relative_visual = view.magnifier_offset_relative

        s.theme = self._get_setting("theme", "auto", str)
        s.current_language = self._get_setting("language", "en", str)
        s.ui_mode = self._get_setting("ui_mode", "beginner", str)
        s.debug_mode_enabled = self._get_setting("debug_mode_enabled", False, bool)
        s.system_notifications_enabled = self._get_setting(
            "system_notifications_enabled", True, bool
        )
        s.auto_crop_black_borders = self._get_setting(
            "auto_crop_black_borders", True, bool
        )
        s.video_recording_fps = self._get_setting("video_recording_fps", 60, int)
        v.session_data.image_state.auto_calculate_psnr = self._get_setting(
            "auto_calculate_psnr", False, bool
        )
        v.session_data.image_state.auto_calculate_ssim = self._get_setting(
            "auto_calculate_ssim", False, bool
        )

        render.divider_line_thickness = self._get_setting("divider_line_thickness", 3, int)
        render.divider_line_color = hex_to_color(
            self._get_setting("divider_line_color", "#FFFFFFFF", str)
        )
        render.divider_line_visible = self._get_setting("divider_line_visible", True, bool)

        render.magnifier_divider_thickness = self._get_setting(
            "magnifier_divider_thickness", 2, int
        )
        render.magnifier_divider_color = hex_to_color(
            self._get_setting("magnifier_divider_color", "#E6FFFFFF", str)
        )
        render.magnifier_divider_visible = self._get_setting(
            "magnifier_divider_visible", True, bool
        )
        render.magnifier_border_color = hex_to_color(
            self._get_setting("magnifier_border_color", "#F8FFFFFF", str)
        )
        render.magnifier_laser_color = hex_to_color(
            self._get_setting("magnifier_laser_color", "#FFFFFFFF", str)
        )
        render.capture_ring_color = hex_to_color(
            self._get_setting("capture_ring_color", "#E6FF3264", str)
        )

        render.magnifier_guides_thickness = self._get_setting(
            "magnifier_guides_thickness", 1, int
        )

        render.font_size_percent = self._get_setting("font_size_percent", 100, int)
        render.font_weight = self._get_setting("font_weight", 0, int)
        render.text_alpha_percent = self._get_setting("text_alpha_percent", 100, int)
        render.file_name_color = hex_to_color(
            self._get_setting("filename_color", "#FFFF0000", str)
        )
        render.file_name_bg_color = hex_to_color(
            self._get_setting("filename_bg_color", "#50000000", str)
        )
        render.draw_text_background = self._get_setting("draw_text_background", True, bool)
        render.text_placement_mode = self._get_setting("text_placement_mode", "edges", str)
        render.include_file_names_in_saved = self._get_setting(
            "include_file_names_in_saved", False, bool
        )

        render.optimize_laser_smoothing = self._get_setting(
            "optimize_laser_smoothing", False, bool
        )
        view.optimize_magnifier_movement = self._get_setting(
            "optimize_magnifier_movement", True, bool
        )

        main_interp = self._get_setting("interpolation_method", "BILINEAR", str)
        render.interpolation_method = main_interp
        render.zoom_interpolation_method = self._get_setting(
            "zoom_interpolation_method", "BILINEAR", str
        )
        logger.debug(
            "SettingsManager.load_all_settings interpolation main=%s zoom=%s",
            main_interp,
            render.zoom_interpolation_method,
        )

        magnifier_movement_interp = self._get_setting(
            "magnifier_movement_interpolation_method", None, str
        )
        laser_smoothing_interp = self._get_setting(
            "laser_smoothing_interpolation_method", None, str
        )

        if magnifier_movement_interp is None:
            movement_interp = self._get_setting(
                "movement_interpolation_method", "BILINEAR", str
            )
            magnifier_movement_interp = movement_interp
            laser_smoothing_interp = movement_interp

        render.magnifier_movement_interpolation_method = (
            magnifier_movement_interp
        )
        render.laser_smoothing_interpolation_method = (
            laser_smoothing_interp or "BILINEAR"
        )

        render.movement_interpolation_method = magnifier_movement_interp

        s.window_width = self._get_setting("window_width", 1024, int)
        s.window_height = self._get_setting("window_height", 768, int)
        s.window_x = self._get_setting("window_x", 100, int)
        s.window_y = self._get_setting("window_y", 100, int)
        s.window_was_maximized = self._get_setting("window_was_maximized", False, bool)

        s.export_use_default_dir = self._get_setting(
            "export_use_default_dir", True, bool
        )
        s.export_default_dir = self._get_setting("export_default_dir", None, str)
        s.export_favorite_dir = self._get_setting("export_favorite_dir", None, str)
        s.export_last_format = self._get_setting("export_last_format", "PNG", str)
        s.export_quality = self._get_setting("export_quality", 95, int)
        s.export_fill_background = self._get_setting(
            "export_fill_background", False, bool
        )
        s.export_background_color = hex_to_color(
            self._get_setting("export_background_color", "#FFFFFFFF", str)
        )
        s.export_last_filename = self._get_setting("export_last_filename", "", str)
        s.export_png_compress_level = self._get_setting(
            "export_png_compress_level", 9, int
        )
        s.export_comment_text = self._get_setting("export_comment_text", "", str)
        s.export_comment_keep_default = self._get_setting(
            "export_comment_keep_default", False, bool
        )
        s.export_video_favorite_dir = self._get_setting(
            "export_video_favorite_dir", None, str
        )
        s.export_video_container = self._get_setting("export_video_container", "mp4", str)
        s.export_video_codec = self._get_setting(
            "export_video_codec", "h264 (AVC)", str
        )
        s.export_video_quality_mode = self._get_setting(
            "export_video_quality_mode", "crf", str
        )
        s.export_video_crf = self._get_setting("export_video_crf", 23, int)
        s.export_video_bitrate = self._get_setting(
            "export_video_bitrate", "8000k", str
        )
        s.export_video_preset = self._get_setting(
            "export_video_preset", "medium", str
        )
        s.export_video_pix_fmt = self._get_setting(
            "export_video_pix_fmt", "yuv420p", str
        )
        s.export_video_manual_args = self._get_setting(
            "export_video_manual_args",
            "-c:v libx264 -crf 23 -pix_fmt yuv420p",
            str,
        )

    def save_all_settings(self, store: Store):
        v, s = store.viewport, store.settings
        render = v.render_config
        view = v.view_state
        self._save_setting("max_name_length", render.max_name_length)
        self._save_setting("display_resolution_limit", render.display_resolution_limit)

        self._save_setting("magnifier_size_relative", view.magnifier_size_relative)
        self._save_setting("capture_size_relative", view.capture_size_relative)
        self._save_setting("magnifier_spacing_relative", view.magnifier_spacing_relative)
        self._save_setting("movement_speed_per_sec", view.movement_speed_per_sec)

        self._save_setting("theme", s.theme)
        self._save_setting("language", s.current_language)
        self._save_setting("ui_mode", s.ui_mode)
        self._save_setting(
            "system_notifications_enabled", s.system_notifications_enabled
        )
        self._save_setting("auto_crop_black_borders", s.auto_crop_black_borders)
        self._save_setting("video_recording_fps", s.video_recording_fps)
        self._save_setting(
            "auto_calculate_psnr", store.viewport.session_data.image_state.auto_calculate_psnr
        )
        self._save_setting(
            "auto_calculate_ssim", store.viewport.session_data.image_state.auto_calculate_ssim
        )

        self._save_setting("divider_line_thickness", render.divider_line_thickness)
        self._save_setting("divider_line_color", color_to_hex(render.divider_line_color))
        self._save_setting("divider_line_visible", render.divider_line_visible)

        self._save_setting("magnifier_divider_thickness", render.magnifier_divider_thickness)
        self._save_setting(
            "magnifier_divider_color", color_to_hex(render.magnifier_divider_color)
        )
        self._save_setting("magnifier_divider_visible", render.magnifier_divider_visible)
        self._save_setting(
            "magnifier_border_color", color_to_hex(render.magnifier_border_color)
        )
        self._save_setting(
            "magnifier_laser_color", color_to_hex(render.magnifier_laser_color)
        )
        self._save_setting(
            "capture_ring_color", color_to_hex(render.capture_ring_color)
        )

        self._save_setting("magnifier_guides_thickness", render.magnifier_guides_thickness)

        self._save_setting("font_size_percent", render.font_size_percent)
        self._save_setting("font_weight", render.font_weight)
        self._save_setting("text_alpha_percent", render.text_alpha_percent)
        self._save_setting("filename_color", color_to_hex(render.file_name_color))
        self._save_setting("filename_bg_color", color_to_hex(render.file_name_bg_color))
        self._save_setting("draw_text_background", render.draw_text_background)
        self._save_setting("text_placement_mode", render.text_placement_mode)
        self._save_setting("include_file_names_in_saved", render.include_file_names_in_saved)

        self._save_setting("optimize_laser_smoothing", render.optimize_laser_smoothing)
        self._save_setting("optimize_magnifier_movement", view.optimize_magnifier_movement)
        self._save_setting("interpolation_method", render.interpolation_method)
        self._save_setting(
            "zoom_interpolation_method", render.zoom_interpolation_method
        )

        self._save_setting(
            "magnifier_movement_interpolation_method",
            render.magnifier_movement_interpolation_method,
        )
        self._save_setting(
            "laser_smoothing_interpolation_method",
            render.laser_smoothing_interpolation_method,
        )

        self._save_setting(
            "movement_interpolation_method", render.movement_interpolation_method
        )

        self._save_setting("window_width", s.window_width)
        self._save_setting("window_height", s.window_height)
        self._save_setting("window_x", s.window_x)
        self._save_setting("window_y", s.window_y)
        self._save_setting("window_was_maximized", s.window_was_maximized)
        self._save_setting("export_use_default_dir", s.export_use_default_dir)
        self._save_setting("export_default_dir", s.export_default_dir)
        self._save_setting("export_favorite_dir", s.export_favorite_dir)
        self._save_setting("export_last_format", s.export_last_format)
        self._save_setting("export_quality", s.export_quality)
        self._save_setting("export_fill_background", s.export_fill_background)
        self._save_setting(
            "export_background_color", color_to_hex(s.export_background_color)
        )
        self._save_setting("export_last_filename", s.export_last_filename)
        self._save_setting("export_png_compress_level", s.export_png_compress_level)
        self._save_setting("export_comment_text", s.export_comment_text)
        self._save_setting(
            "export_comment_keep_default", s.export_comment_keep_default
        )
        self._save_setting("export_video_favorite_dir", s.export_video_favorite_dir)
        self._save_setting("export_video_container", s.export_video_container)
        self._save_setting("export_video_codec", s.export_video_codec)
        self._save_setting("export_video_quality_mode", s.export_video_quality_mode)
        self._save_setting("export_video_crf", s.export_video_crf)
        self._save_setting("export_video_bitrate", s.export_video_bitrate)
        self._save_setting("export_video_preset", s.export_video_preset)
        self._save_setting("export_video_pix_fmt", s.export_video_pix_fmt)
        self._save_setting("export_video_manual_args", s.export_video_manual_args)

        self.settings.sync()

    def _save_setting(self, key, value):
        if value is None:
            return
        self.settings.setValue(key, value)

    def is_first_run(self) -> bool:
        return self._get_setting("is_first_run", True, bool)

    def set_first_run_completed(self):
        self._save_setting("is_first_run", False)
