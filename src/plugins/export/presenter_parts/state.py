from __future__ import annotations

import os
import re
from pathlib import Path

from domain.types import Color
from plugins.export.models import ExportDialogState

class ExportStateCoordinator:
    def __init__(self, store, main_controller, main_window_app):
        self.store = store
        self.main_controller = main_controller
        self.main_window_app = main_window_app

    def get_os_default_downloads(self) -> str:
        if hasattr(self.main_window_app, "_get_os_default_downloads"):
            return self.main_window_app._get_os_default_downloads()
        return str(Path.home() / "Downloads")

    def get_unique_filepath(
        self, directory: str, base_name: str, extension: str
    ) -> str:
        full_path = os.path.join(directory, f"{base_name}{extension}")
        if not os.path.exists(full_path):
            return full_path

        counter = 1
        while True:
            new_name = f"{base_name} ({counter})"
            new_path = os.path.join(directory, f"{new_name}{extension}")
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def color_from_tuple(self, color_tuple):
        if color_tuple is None:
            return Color(255, 255, 255, 255)
        return Color(*color_tuple)

    def default_bg_color(self):
        return Color(255, 255, 255, 255)

    def resolve_quick_save_output_dir(self) -> str:
        settings = self.store.settings
        if (
            getattr(settings, "export_use_default_dir", True)
            and getattr(settings, "export_default_dir", None)
        ):
            return settings.export_default_dir

        favorite_dir = getattr(settings, "export_favorite_dir", None)
        if favorite_dir:
            return favorite_dir

        default_dir = getattr(settings, "export_default_dir", None)
        if default_dir:
            return default_dir

        return self.get_os_default_downloads()

    def build_export_dialog_state(self) -> ExportDialogState:
        settings = self.store.settings
        return ExportDialogState(
            current_language=settings.current_language,
            output_dir=(
                getattr(settings, "export_default_dir", None)
                or self.get_os_default_downloads()
            ),
            favorite_dir=getattr(settings, "export_favorite_dir", None),
            last_format=(getattr(settings, "export_last_format", "PNG") or "PNG"),
            quality=int(getattr(settings, "export_quality", 95) or 95),
            png_compress_level=int(
                getattr(settings, "export_png_compress_level", 9) or 9
            ),
            fill_background=bool(getattr(settings, "export_fill_background", False)),
            background_color=getattr(settings, "export_background_color", None),
            comment_text=getattr(settings, "export_comment_text", "") or "",
            comment_keep_default=bool(
                getattr(settings, "export_comment_keep_default", False)
            ),
        )

    def set_export_favorite_dir(self, path: str) -> None:
        self.store.settings.export_favorite_dir = path
        if (
            self.main_controller is not None
            and self.main_controller.settings_manager is not None
        ):
            self.main_controller.settings_manager._save_setting(
                "export_favorite_dir", path
            )

    def build_suggested_export_filename(self) -> str:
        name1 = (self.get_current_display_name(1) or "image1").strip()
        name2 = (self.get_current_display_name(2) or "image2").strip()
        base_name = (
            f"{self.sanitize_export_name(name1)}_"
            f"{self.sanitize_export_name(name2)}"
        )
        out_dir = self.store.settings.export_default_dir or self.get_os_default_downloads()
        fmt = (self.store.settings.export_last_format or "PNG").upper()
        ext = "." + fmt.lower().replace("jpeg", "jpg")
        unique_full_path = self.get_unique_filepath(out_dir, base_name, ext)
        return os.path.splitext(os.path.basename(unique_full_path))[0]

    def sanitize_export_name(self, value: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", value)[:80]

    def persist_export_settings(self, export_opts: dict) -> None:
        settings = self.store.settings
        settings.export_last_format = export_opts.get("format", "PNG")
        settings.export_quality = int(export_opts.get("quality", 95))
        settings.export_fill_background = bool(
            export_opts.get("fill_background", False)
        )
        bg_color = export_opts.get("background_color")
        settings.export_background_color = (
            self.color_from_tuple(bg_color) if bg_color else self.default_bg_color()
        )
        settings.export_last_filename = export_opts["file_name"]
        settings.export_default_dir = export_opts["output_dir"]
        settings.export_png_compress_level = int(
            export_opts.get("png_compress_level", 9)
        )
        if bool(export_opts.get("comment_keep_default", False)):
            settings.export_comment_text = export_opts.get("comment_text", "")
            settings.export_comment_keep_default = True
        else:
            settings.export_comment_text = ""
            settings.export_comment_keep_default = False

        if self.main_controller and hasattr(self.main_controller, "settings_manager"):
            self.main_controller.settings_manager.save_all_settings(self.store)

    def build_quick_export_options(self) -> dict:
        bg_color = getattr(
            self.store.settings, "export_background_color", self.default_bg_color()
        )
        bg_color_tuple = (bg_color.r, bg_color.g, bg_color.b, bg_color.a)
        name1 = (self.get_current_display_name(1) or "image1").strip()
        name2 = (self.get_current_display_name(2) or "image2").strip()
        base_name = (
            f"{self.sanitize_export_name(name1)}_"
            f"{self.sanitize_export_name(name2)}"
        )

        return {
            "output_dir": self.resolve_quick_save_output_dir(),
            "file_name": base_name,
            "format": self.store.settings.export_last_format or "PNG",
            "quality": self.store.settings.export_quality or 95,
            "fill_background": getattr(
                self.store.settings, "export_fill_background", False
            ),
            "background_color": bg_color_tuple,
            "png_compress_level": getattr(
                self.store.settings, "export_png_compress_level", 9
            ),
            "png_optimize": True,
            "include_metadata": bool(
                getattr(self.store.settings, "export_comment_keep_default", False)
            ),
            "comment_text": (
                getattr(self.store.settings, "export_comment_text", "")
                if getattr(self.store.settings, "export_comment_keep_default", False)
                else ""
            ),
            "is_quick_save": True,
        }

    def get_current_display_name(self, image_number: int) -> str:
        target_list, index = (
            (self.store.document.image_list1, self.store.document.current_index1)
            if image_number == 1
            else (self.store.document.image_list2, self.store.document.current_index2)
        )
        if 0 <= index < len(target_list):
            return target_list[index].display_name
        return ""
