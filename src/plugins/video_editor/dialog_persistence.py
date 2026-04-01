import os
from pathlib import Path

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog

from domain.qt_adapters import color_to_hex, hex_to_color, qcolor_to_color

class VideoEditorDialogPersistence:
    def __init__(self, dialog):
        self.dialog = dialog

    def get_settings_refs(self):
        d = self.dialog
        store = None
        settings_manager = None
        if d.export_controller and hasattr(d.export_controller, "store"):
            store = d.export_controller.store
        if d.export_controller and hasattr(d.export_controller, "presenter"):
            main_controller = getattr(d.export_controller.presenter, "main_controller", None)
            if main_controller is not None:
                settings_manager = getattr(main_controller, "settings_manager", None)
                if store is None:
                    store = getattr(main_controller, "store", None)
        return store, settings_manager

    def load_export_settings(self):
        d = self.dialog
        store, settings_manager = self.get_settings_refs()
        settings = getattr(store, "settings", None)
        if settings is None:
            d._on_container_changed(d.combo_container.currentText())
            return
        d.edit_manual_args.setText(getattr(settings, "export_video_manual_args", d.edit_manual_args.text()))
        d.edit_crf.setText(str(getattr(settings, "export_video_crf", 23)))
        d.edit_bitrate.setText(getattr(settings, "export_video_bitrate", d.edit_bitrate.text()))

        container = getattr(settings, "export_video_container", "mp4")
        idx = d.combo_container.findData(container)
        if idx >= 0:
            d.combo_container.setCurrentIndex(idx)
        d._on_container_changed(d.combo_container.currentText())

        codec = getattr(settings, "export_video_codec", "h264 (AVC)")
        idx = d.combo_codec.findData(codec)
        if idx >= 0:
            d.combo_codec.setCurrentIndex(idx)
        d._on_codec_changed(d.combo_codec.currentText())

        quality_mode = getattr(settings, "export_video_quality_mode", "crf")
        idx = d.combo_quality_mode.findData(quality_mode)
        if idx >= 0:
            d.combo_quality_mode.setCurrentIndex(idx)
            d.stack_quality.setCurrentIndex(idx)

        for combo, attr, default in (
            (d.combo_preset, "export_video_preset", "medium"),
            (d.combo_pix_fmt, "export_video_pix_fmt", "yuv420p"),
        ):
            idx = combo.findData(getattr(settings, attr, default))
            if idx >= 0:
                combo.setCurrentIndex(idx)

        fill_color_hex = getattr(settings, "export_video_fit_fill_color", None)
        if not fill_color_hex and settings_manager is not None:
            fill_color_hex = settings_manager._get_setting("export_video_fit_fill_color", "#FF000000", str)
        try:
            d.fit_content_fill_color = QColor(color_to_hex(hex_to_color(fill_color_hex or "#FF000000")))
        except Exception:
            d.fit_content_fill_color = QColor(0, 0, 0, 255)
        d._update_fit_fill_color_button()
        if hasattr(d, "btn_fit_fill_color"):
            d.btn_fit_fill_color.setVisible(d.btn_fit_content.isChecked())

    def connect_export_settings_persistence(self):
        d = self.dialog
        for signal in (
            d.combo_container.currentIndexChanged,
            d.combo_codec.currentIndexChanged,
            d.combo_quality_mode.currentIndexChanged,
            d.combo_preset.currentIndexChanged,
            d.combo_pix_fmt.currentIndexChanged,
            d.edit_crf.textChanged,
            d.edit_bitrate.textChanged,
            d.edit_manual_args.textChanged,
        ):
            signal.connect(lambda *_: self.persist_export_settings())

    def persist_export_settings(self):
        d = self.dialog
        store, settings_manager = self.get_settings_refs()
        settings = getattr(store, "settings", None)
        if settings is None:
            return
        settings.export_video_container = d.combo_container.currentData() or "mp4"
        settings.export_video_codec = d.combo_codec.currentData() or "h264 (AVC)"
        settings.export_video_quality_mode = d.combo_quality_mode.currentData() or "crf"
        settings.export_video_crf = int(d.edit_crf.text()) if d.edit_crf.text().isdigit() else 23
        settings.export_video_bitrate = d.edit_bitrate.text().strip() or "8000k"
        settings.export_video_preset = d.combo_preset.currentData() or ""
        settings.export_video_pix_fmt = d.combo_pix_fmt.currentData() or ""
        settings.export_video_manual_args = d.edit_manual_args.text()
        settings.export_video_fit_fill_color = color_to_hex(qcolor_to_color(d.fit_content_fill_color))
        if settings_manager is None:
            return
        for key in (
            "container",
            "codec",
            "quality_mode",
            "crf",
            "bitrate",
            "preset",
            "pix_fmt",
            "manual_args",
            "fit_fill_color",
        ):
            settings_manager._save_setting(
                f"export_video_{key}", getattr(settings, f"export_video_{key}")
            )

    def browse_output_dir(self):
        d = self.dialog
        current_dir = d.edit_output_dir.text() if hasattr(d, "edit_output_dir") else ""
        if not current_dir or not os.path.isdir(current_dir):
            if d.export_controller and hasattr(d.export_controller, "store") and d.export_controller.store:
                current_dir = d.export_controller.store.settings.export_default_dir or ""
            if not current_dir:
                current_dir = str(Path.home() / "Downloads")
        selected_dir = QFileDialog.getExistingDirectory(
            d,
            d._tr("export.select_output_directory"),
            current_dir,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog,
        )
        if selected_dir:
            d.edit_output_dir.setText(selected_dir)
            d.edit_output_dir.setCursorPosition(0)

    def on_set_favorite_clicked(self):
        d = self.dialog
        current_path = d.edit_output_dir.text().strip()
        if current_path and d.presenter:
            d.presenter.set_favorite_path(current_path)

    def on_use_favorite_clicked(self):
        d = self.dialog
        if not d.presenter:
            return
        favorite_path = d.presenter.get_favorite_path()
        if favorite_path and os.path.isdir(favorite_path):
            d.edit_output_dir.setText(favorite_path)
            d.edit_output_dir.setCursorPosition(0)
