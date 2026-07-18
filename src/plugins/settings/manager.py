import logging

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

from core.constants import AppConstants
from core.store import Store
from domain.qt_adapters import hex_to_color, color_to_hex
from ui.canvas_infra.scene.property_access import (
    deserialize_canvas_feature_setting,
    read_canvas_feature_property,
    write_canvas_feature_property,
    serialize_canvas_feature_setting,
)
from ui.canvas_infra.scene.registry import get_canvas_registry

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

        view.movement_speed_per_sec = self._get_setting(
            "movement_speed_per_sec", 2.0, float
        )

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
        s.video_editor_preview_render_scale = self._get_setting(
            "video_editor_preview_render_scale", 1.0, float
        )
        s.show_workspace_tabs = self._get_setting("show_workspace_tabs", True, bool)
        s.rhi_backend = self._get_setting("rhi_backend", "default", str)
        s.keyboard_overrides = self._load_keyboard_overrides()

        render.font_size_percent = self._get_setting("font_size_percent", 120, int)
        render.font_weight = self._get_setting("font_weight", 0, int)
        render.text_alpha_percent = self._get_setting("text_alpha_percent", 100, int)
        render.file_name_color = hex_to_color(
            self._get_setting("filename_color", "#FFFF0000", str)
        )
        render.file_name_bg_color = hex_to_color(
            self._get_setting("filename_bg_color", "#FF000000", str)
        )
        render.draw_text_background = self._get_setting("draw_text_background", True, bool)
        render.text_placement_mode = self._get_setting("text_placement_mode", "edges", str)
        render.include_file_names_in_saved = self._get_setting(
            "include_file_names_in_saved", False, bool
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

        self._load_canvas_feature_settings(v)
        self._load_tab_canvas_feature_settings(store)

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
        s.export_suppress_untested_resolution_warning = self._get_setting(
            "export_suppress_untested_resolution_warning", False, bool
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

        self._save_tab_canvas_feature_settings(store)

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
            "video_editor_preview_render_scale",
            s.video_editor_preview_render_scale,
        )
        self._save_setting("show_workspace_tabs", s.show_workspace_tabs)
        self._save_setting("rhi_backend", s.rhi_backend)
        self._save_keyboard_overrides(s.keyboard_overrides)

        self._save_setting("font_size_percent", render.font_size_percent)
        self._save_setting("font_weight", render.font_weight)
        self._save_setting("text_alpha_percent", render.text_alpha_percent)
        self._save_setting("filename_color", color_to_hex(render.file_name_color))
        self._save_setting("filename_bg_color", color_to_hex(render.file_name_bg_color))
        self._save_setting("draw_text_background", render.draw_text_background)
        self._save_setting("text_placement_mode", render.text_placement_mode)
        self._save_setting("include_file_names_in_saved", render.include_file_names_in_saved)

        self._save_setting("interpolation_method", render.interpolation_method)
        self._save_setting(
            "zoom_interpolation_method", render.zoom_interpolation_method
        )

        self._save_canvas_feature_settings(v)

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
        self._save_setting(
            "export_suppress_untested_resolution_warning",
            s.export_suppress_untested_resolution_warning,
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

    def _iter_all_canvas_feature_properties(self):
        from tabs.registry import TabRegistry

        tab_registry = TabRegistry()
        tab_registry.discover()
        seen_keys: set[str] = set()
        for tab_type in tab_registry.registered_types:
            for prop in get_canvas_registry(tab_type).get_feature_properties():
                if not prop.setting_key or prop.setting_key in seen_keys:
                    continue
                seen_keys.add(prop.setting_key)
                yield prop

    def _load_canvas_feature_settings(self, viewport_state) -> None:
        for prop in self._iter_all_canvas_feature_properties():
            if not self.settings.contains(prop.setting_key):
                continue
            raw_value = self.settings.value(prop.setting_key)
            channels = deserialize_canvas_feature_setting(prop, raw_value)
            write_canvas_feature_property(viewport_state, prop, channels)

    def _save_canvas_feature_settings(self, viewport_state) -> None:
        for prop in self._iter_all_canvas_feature_properties():
            channels = read_canvas_feature_property(viewport_state, prop)
            raw_value = serialize_canvas_feature_setting(prop, channels)
            self._save_setting(prop.setting_key, raw_value)

    def _load_tab_canvas_feature_settings(self, store: Store) -> None:
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        registry.create_service(
            "settings_canvas_feature_load",
            store,
            self._get_setting,
        )

    def _save_tab_canvas_feature_settings(self, store: Store) -> None:
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        registry.create_service(
            "settings_canvas_feature_save",
            store,
            self._save_setting,
        )

    def _load_keyboard_overrides(self) -> dict[str, str]:
        import json

        raw = self.settings.value("keyboard_overrides", "")
        if not raw:
            return {}
        try:
            if isinstance(raw, dict):
                data = raw
            else:
                data = json.loads(str(raw))
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_keyboard_overrides(self, overrides: dict[str, str]) -> None:
        import json

        self.settings.setValue("keyboard_overrides", json.dumps(dict(overrides or {})))

    def _save_setting(self, key, value):
        if value is None:
            return
        self.settings.setValue(key, value)

    def is_first_run(self) -> bool:
        if not self.settings.contains("is_first_run"):
            return True
        val = self.settings.value("is_first_run")
        if isinstance(val, bool):
            return val
        text = str(val).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return True

    def set_first_run_completed(self):
        self._save_setting("is_first_run", False)
