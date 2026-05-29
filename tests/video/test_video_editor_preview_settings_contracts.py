"""Video preview-quality settings: i18n keys exist for every language, the UI
uses translation keys only (no hardcoded strings), and the chosen scale
persists and reloads.

Dogma source: docs/dev/HELP_WIDGET.md §i18n/help discipline.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtGui import QColor

from plugins.video_editor.dialog_persistence import VideoEditorDialogPersistence


REPO = Path(__file__).resolve().parents[2]
I18N_ROOT = REPO / "src" / "resources" / "i18n"
PREVIEW_QUALITY_KEYS = {
    "preview_quality",
    "preview_quality_full",
    "preview_quality_balanced",
    "preview_quality_performance",
    "preview_quality_draft",
}


def test_video_preview_quality_i18n_keys_exist_for_all_languages():
    """HELP_WIDGET.md: user-facing video editor labels must live in i18n resources."""
    video_files = sorted(I18N_ROOT.glob("*/features/video.json"))
    assert video_files

    for path in video_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        video = data.get("video", {})
        missing = PREVIEW_QUALITY_KEYS.difference(video)
        assert not missing, f"{path}: missing {sorted(missing)}"
        for key in PREVIEW_QUALITY_KEYS:
            assert isinstance(video[key], str) and video[key].strip()


def test_preview_quality_settings_use_translation_keys_only():
    """HELP_WIDGET.md: UI construction must not hardcode translated preview labels."""
    source = (REPO / "src" / "plugins" / "video_editor" / "dialog_sections.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden = {
        "Preview Quality:",
        "Preview Quality",
        "Full (1.0x)",
        "Balanced (0.75x)",
        "Performance (0.5x)",
        "Draft (0.25x)",
    }

    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert forbidden.isdisjoint(constants)
    for key in PREVIEW_QUALITY_KEYS:
        assert f"video.{key}" in constants


class _FakeSignal:
    def connect(self, _callback):
        return None


class _FakeCombo:
    def __init__(self, values):
        self._values = list(values)
        self._index = 0
        self.currentIndexChanged = _FakeSignal()

    def findData(self, value):
        for index, item in enumerate(self._values):
            if item == value:
                return index
        return -1

    def setCurrentIndex(self, index):
        self._index = int(index)

    def currentData(self):
        return self._values[self._index]

    def currentText(self):
        return str(self.currentData())


class _FakeLineEdit:
    textChanged = _FakeSignal()

    def __init__(self, value=""):
        self._value = str(value)

    def setText(self, value):
        self._value = str(value)

    def text(self):
        return self._value


class _FakeStack:
    def __init__(self):
        self.index = 0

    def setCurrentIndex(self, index):
        self.index = int(index)


class _FakeButton:
    def __init__(self):
        self.visible = None

    def isChecked(self):
        return False

    def setVisible(self, visible):
        self.visible = bool(visible)


class _FakeSettingsManager:
    def __init__(self):
        self.saved = {}

    def _save_setting(self, key, value):
        self.saved[key] = value

    def _get_setting(self, _key, default, _type):
        return default


def _settings(preview_scale=1.0):
    return SimpleNamespace(
        export_video_manual_args="",
        export_video_crf=23,
        export_video_bitrate="8000k",
        export_video_container="mp4",
        export_video_codec="h264 (AVC)",
        export_video_quality_mode="crf",
        export_video_preset="medium",
        export_video_pix_fmt="yuv420p",
        video_editor_preview_render_scale=preview_scale,
        export_video_fit_fill_color="#FF000000",
    )


def _dialog(settings, *, preview_index=0):
    dialog = SimpleNamespace()
    dialog.export_controller = SimpleNamespace(store=SimpleNamespace(settings=settings))
    dialog.edit_manual_args = _FakeLineEdit()
    dialog.edit_crf = _FakeLineEdit("23")
    dialog.edit_bitrate = _FakeLineEdit("8000k")
    dialog.combo_container = _FakeCombo(["mp4"])
    dialog.combo_codec = _FakeCombo(["h264 (AVC)"])
    dialog.combo_quality_mode = _FakeCombo(["crf", "bitrate"])
    dialog.combo_preset = _FakeCombo(["medium"])
    dialog.combo_pix_fmt = _FakeCombo(["yuv420p"])
    dialog.combo_preview_scale = _FakeCombo([1.0, 0.75, 0.5, 0.25])
    dialog.combo_preview_scale.setCurrentIndex(preview_index)
    dialog.stack_quality = _FakeStack()
    dialog.fit_content_fill_color = QColor(0, 0, 0, 255)
    dialog.btn_fit_content = _FakeButton()
    dialog.btn_fit_fill_color = _FakeButton()
    dialog.preview_scale_events = []
    dialog._on_container_changed = lambda _text: None
    dialog._on_codec_changed = lambda _text: None
    dialog._update_fit_fill_color_button = lambda: None
    dialog._on_preview_scale_changed = lambda: dialog.preview_scale_events.append(
        float(dialog.combo_preview_scale.currentData())
    )
    return dialog


def test_preview_quality_setting_persists_and_loads_roundtrip():
    """TESTING.md: video editor preview settings need a behavior-level roundtrip test."""
    settings = _settings(preview_scale=1.0)
    dialog = _dialog(settings, preview_index=2)
    persistence = VideoEditorDialogPersistence(dialog)
    settings_manager = _FakeSettingsManager()
    persistence.get_settings_refs = lambda: (dialog.export_controller.store, settings_manager)

    persistence.persist_export_settings()

    assert settings.video_editor_preview_render_scale == 0.5
    assert settings_manager.saved["video_editor_preview_render_scale"] == 0.5

    reloaded_dialog = _dialog(settings, preview_index=0)
    reloaded = VideoEditorDialogPersistence(reloaded_dialog)
    reloaded.get_settings_refs = lambda: (
        reloaded_dialog.export_controller.store,
        settings_manager,
    )

    reloaded.load_export_settings()

    assert reloaded_dialog.combo_preview_scale.currentData() == 0.5
    assert reloaded_dialog.preview_scale_events == [0.5]
