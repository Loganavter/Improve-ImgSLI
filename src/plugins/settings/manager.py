import logging
import os
import shutil

from PySide6.QtCore import QSettings, QTimer
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
        self._organization_name = organization_name
        self._application_name = application_name
        self.settings = QSettings(organization_name, application_name)
        self._backup_path = self.settings.fileName() + ".backup"
        logger.debug(
            "[settings] SettingsManager init file=%s backup=%s",
            self.settings.fileName(),
            self._backup_path,
        )
        if self._restore_backup_if_corrupt():
            # The QSettings instance cached the corrupt state; re-read the
            # restored file with a fresh instance.
            self.settings = QSettings(organization_name, application_name)
            self._backup_path = self.settings.fileName() + ".backup"

    def _caller_summary(self) -> str:
        """Last 3 non-manager call frames, for load/save origin tracing.

        Settings resets are reported as "random" — the value of this log is
        catching *which* code path triggered a load/save, not just that one
        happened.
        """
        try:
            import traceback

            here = os.path.abspath(__file__)
            # extract_stack is ordered outermost-first; keep the nearest 3
            # non-manager frames and print nearest-first so the log reads
            # "who called us" -> "who called them".
            frames = [
                frame
                for frame in traceback.extract_stack()[:-1]
                if os.path.abspath(frame.filename) != here
            ][-3:]
            return " <- ".join(
                f"{os.path.basename(frame.filename)}:{frame.lineno}:{frame.name}"
                for frame in reversed(frames)
            )
        except Exception:
            return "unknown"

    def _restore_backup_if_corrupt(self) -> bool:
        """Heal a truncated/corrupt settings file from the last-good backup.

        QSettings writes its INI in place (open-truncate-write-close), so a
        kill/crash mid-save leaves a truncated file. The next startup then
        loads defaults and a clean exit re-writes them — permanently wiping
        the user's settings (observed: language and UI prefs reset to
        defaults after dev iterations that kill the app). A startup that
        finds the file present but missing the critical keys restores the
        ``.backup`` copy instead.
        """
        path = self.settings.fileName()
        if not os.path.exists(path):
            return False
        keys = len(self.settings.allKeys())
        logger.debug(
            "[settings] health check: file=%s keys=%d backup=%s",
            path,
            keys,
            os.path.exists(self._backup_path),
        )
        if self.settings.contains("language") or self.settings.contains("theme"):
            return False
        if not os.path.exists(self._backup_path):
            logger.warning(
                "Settings file looks empty/corrupt but no .backup exists to "
                "restore from: %s",
                path,
            )
            return False
        try:
            shutil.copy2(self._backup_path, path)
            logger.warning(
                "Settings file was corrupt/truncated; restored from backup: %s",
                path,
            )
            return True
        except Exception:
            logger.exception("Failed to restore settings from backup %s", self._backup_path)
            return False

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
        logger.debug(
            "[settings] load_all_settings START caller=%s file=%s keys_in_file=%d",
            self._caller_summary(),
            self.settings.fileName(),
            len(self.settings.allKeys()),
        )

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
        s.ui_scale_factor = self._get_setting("ui_scale_factor", 1.0, float)
        s.ui_font_mode = self._get_setting("ui_font_mode", "builtin", str)
        s.ui_font_family = self._get_setting("ui_font_family", "", str)
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
        logger.debug(
            "[settings] load_all_settings DONE theme=%s language=%s ui_mode=%s "
            "ui_scale=%s window=%dx%d keys_in_file=%d",
            s.theme,
            s.current_language,
            s.ui_mode,
            s.ui_scale_factor,
            s.window_width,
            s.window_height,
            len(self.settings.allKeys()),
        )

    def schedule_persist(self, store: Store) -> None:
        """Debounced full-snapshot save — the single writer for dialog-apply
        state (coalesced: repeated calls within the debounce window save once).

        The settings file must only ever be written as a coherent snapshot of
        the authoritative Store. Writing individual keys from UI state (the
        previous ``apply()`` behavior) allowed a stale dialog widget to
        silently overwrite good values with its defaults — the observed
        "random settings reset" (ui_mode/scale/rhi reverted). Callers that
        mutate the Store (dispatches) call this; the snapshot then reflects
        whatever the Store holds.
        """
        if getattr(self, "_persist_pending", False):
            return
        self._persist_pending = True

        def _run() -> None:
            self._persist_pending = False
            try:
                self.save_all_settings(store)
            except Exception:
                logger.exception("[settings] scheduled full persist failed")

        QTimer.singleShot(150, _run)

    def save_all_settings(self, store: Store):
        v, s = store.viewport, store.settings
        render = v.render_config
        view = v.view_state
        logger.debug(
            "[settings] save_all_settings START caller=%s file=%s "
            "store_digest=theme=%s language=%s ui_mode=%s ui_scale=%s "
            "window=%dx%d rhi_backend=%s",
            self._caller_summary(),
            self.settings.fileName(),
            s.theme,
            s.current_language,
            s.ui_mode,
            s.ui_scale_factor,
            s.window_width,
            s.window_height,
            s.rhi_backend,
        )
        self._save_setting("max_name_length", render.max_name_length)
        self._save_setting("display_resolution_limit", render.display_resolution_limit)

        self._save_tab_canvas_feature_settings(store)

        self._save_setting("movement_speed_per_sec", view.movement_speed_per_sec)

        self._save_setting("theme", s.theme)
        self._save_setting("language", s.current_language)
        self._save_setting("ui_mode", s.ui_mode)
        self._save_setting("ui_scale_factor", s.ui_scale_factor)
        self._save_setting("ui_font_mode", s.ui_font_mode)
        self._save_setting("ui_font_family", s.ui_font_family)
        self._save_setting("debug_mode_enabled", s.debug_mode_enabled)
        self._save_setting(
            "system_notifications_enabled", s.system_notifications_enabled
        )
        self._save_setting("auto_crop_black_borders", s.auto_crop_black_borders)
        self._save_setting("video_recording_fps", s.video_recording_fps)
        self._save_setting(
            "video_editor_preview_render_scale",
            s.video_editor_preview_render_scale,
        )
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
        self._refresh_backup()
        logger.debug(
            "[settings] save_all_settings DONE keys_in_file=%d backup=%s",
            len(self.settings.allKeys()),
            self._backup_path,
        )

    def _refresh_backup(self) -> None:
        """Keep a last-good copy of the settings file next to it.

        Refreshed after every successful save so the startup self-heal
        (``_restore_backup_if_corrupt``) restores recent settings rather
        than stale ones.
        """
        try:
            path = self.settings.fileName()
            if os.path.exists(path):
                shutil.copy2(path, self._backup_path)
                logger.debug("[settings] backup refreshed: %s", self._backup_path)
        except Exception:
            logger.debug("Settings backup refresh failed", exc_info=True)

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
            logger.debug(
                "[settings] skip saving %s (None) caller=%s",
                key,
                self._caller_summary(),
            )
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

    def last_seen_app_version(self) -> str:
        """Version string recorded the last time this profile ran, or ""
        if never recorded. Existing installs from before this tracking
        existed also read back "" here -- see
        ``core.bootstrap.ApplicationContext._maybe_flag_cache_purge_notice``,
        which uses that (combined with ``is_first_run()`` being False) to
        tell "genuinely fresh install" apart from "upgraded from an
        untracked version"."""
        return self._get_setting("last_seen_app_version", "", str)

    def set_last_seen_app_version(self, version: str) -> None:
        self._save_setting("last_seen_app_version", version)