import os
import re

from plugins.video_editor.services.export_config import ExportConfigBuilder

from .common import default_downloads_dir

class OutputPathCoordinator:
    def __init__(self, view, main_controller, editor_service, model):
        self.view = view
        self.main_controller = main_controller
        self.editor_service = editor_service
        self.model = model

    def detach_view(self):
        self.view = None

    def initialize_output_fields(self):
        if self.view is None:
            return
        if not hasattr(self.view, "edit_output_dir") or not hasattr(
            self.view, "edit_filename"
        ):
            return

        output_dir = ""
        if self.main_controller and getattr(self.main_controller, "store", None):
            favorite_dir = getattr(
                self.main_controller.store.settings, "export_video_favorite_dir", None
            )
            if favorite_dir and os.path.isdir(favorite_dir):
                output_dir = favorite_dir

        if not output_dir and self.main_controller and getattr(
            self.main_controller, "store", None
        ):
            output_dir = self.main_controller.store.settings.export_default_dir or ""

        if not output_dir:
            output_dir = default_downloads_dir()

        self.view.edit_output_dir.setText(output_dir)
        self.view.edit_output_dir.setCursorPosition(0)

        suggested_name = self.generate_suggested_name()
        self.view.edit_filename.setText(suggested_name)
        self.view.edit_filename.setCursorPosition(0)
        self.refresh_unique_output_filename()

    def current_output_extension(self) -> str:
        if self.view is None:
            return "mp4"
        container = ""
        if hasattr(self.view, "combo_container") and self.view.combo_container is not None:
            container = self.view.combo_container.currentData() or ""
        container = str(container or "mp4").strip().lower()
        return container or "mp4"

    def unique_output_filepath(
        self, directory: str, base_name: str, extension: str
    ) -> str:
        full_path = os.path.join(directory, f"{base_name}.{extension}")
        if not os.path.exists(full_path):
            return full_path

        counter = 1
        while True:
            candidate_name = f"{base_name} ({counter})"
            candidate_path = os.path.join(directory, f"{candidate_name}.{extension}")
            if not os.path.exists(candidate_path):
                return candidate_path
            counter += 1

    def refresh_unique_output_filename(self) -> None:
        if self.view is None:
            return
        if not hasattr(self.view, "edit_output_dir") or not hasattr(
            self.view, "edit_filename"
        ):
            return

        output_dir = self.view.edit_output_dir.text().strip()
        raw_name = self.view.edit_filename.text().strip() or self.generate_suggested_name()
        extension = self.current_output_extension()

        suffix = f".{extension}"
        if raw_name.lower().endswith(suffix):
            raw_name = raw_name[: -len(suffix)].rstrip()
        if not raw_name:
            raw_name = self.generate_suggested_name()

        unique_path = self.unique_output_filepath(output_dir or "", raw_name, extension)
        unique_name = os.path.splitext(os.path.basename(unique_path))[0]
        if unique_name == self.view.edit_filename.text().strip():
            return

        cursor_pos = self.view.edit_filename.cursorPosition()
        self.view.edit_filename.blockSignals(True)
        self.view.edit_filename.setText(unique_name)
        self.view.edit_filename.setCursorPosition(min(cursor_pos, len(unique_name)))
        self.view.edit_filename.blockSignals(False)

    def generate_suggested_name(self) -> str:
        snaps = self.editor_service.get_current_snapshots()
        if not snaps:
            return "video_export"

        snap = snaps[0]
        name1 = snap.name1 if snap.name1 else "img1"
        name2 = snap.name2 if snap.name2 else "img2"
        return f"{self._sanitize(name1)}_{self._sanitize(name2)}"

    def set_favorite_path(self, path):
        if self.main_controller and getattr(self.main_controller, "store", None):
            self.main_controller.store.settings.export_video_favorite_dir = path
            if hasattr(self.main_controller, "settings_manager"):
                self.main_controller.settings_manager._save_setting(
                    "export_video_favorite_dir", path
                )

    def get_favorite_path(self):
        if self.main_controller and getattr(self.main_controller, "store", None):
            return getattr(
                self.main_controller.store.settings, "export_video_favorite_dir", None
            )
        return None

    def on_container_changed(self, container: str):
        if self.view is None:
            return
        self.model.container = container
        codecs = ExportConfigBuilder.get_codecs_for_container(container)
        default_codec = ExportConfigBuilder.get_default_codec_for_container(container)
        self.view.update_available_codecs(codecs, default_codec)
        self.refresh_unique_output_filename()

    @staticmethod
    def _sanitize(text: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", str(text))[:40].strip()
