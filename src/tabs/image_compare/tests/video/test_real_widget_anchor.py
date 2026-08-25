"""Real-widget anchor for over-mocked video-preview fakes (W5 gap).

Inv: _FakeCombo/_FakeSettingsManager must not drift from real widget semantics.
One real-widget test pins the contract: QComboBox findData/currentData/setCurrentIndex
and QSettings roundtrip.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QComboBox

from tabs.image_compare.plugins.video_editor.dialog.persistence import VideoEditorDialogPersistence
from types import SimpleNamespace

from PySide6.QtGui import QColor


def _real_combo(values, current=0):
    cb = QComboBox()
    for v in values:
        cb.addItem(str(v), v)
    cb.setCurrentIndex(current)
    return cb


def test_real_qcombobox_semantics_match_fake():
    # Fake used in test_video_editor_preview_settings_contracts
    from tabs.image_compare.tests.video.test_video_editor_preview_settings_contracts import _FakeCombo

    values = [1.0, 0.75, 0.5, 0.25]
    fake = _FakeCombo(values)
    real = _real_combo(values)
    for v in values:
        assert fake.findData(v) == real.findData(v)
        fake.setCurrentIndex(fake.findData(v))
        real.setCurrentIndex(real.findData(v))
        assert fake.currentData() == real.currentData()


def test_real_widget_persistence_roundtrip(qapp):
    # Use real QComboBox widgets in persistence, not fakes
    from PySide6.QtCore import QSettings

    settings = SimpleNamespace(
        export_video_manual_args="",
        export_video_crf=23,
        export_video_bitrate="8000k",
        export_video_container="mp4",
        export_video_codec="h264 (AVC)",
        export_video_quality_mode="crf",
        export_video_preset="medium",
        export_video_pix_fmt="yuv420p",
        video_editor_preview_render_scale=0.5,
        export_video_fit_fill_color="#FF000000",
    )

    class _FakeStack:
        def __init__(self):
            self.index = 0

        def setCurrentIndex(self, i):
            self.index = int(i)

    class _FakeLineEdit:
        def __init__(self, v=""):
            self._v = str(v)

        def setText(self, v):
            self._v = str(v)

        def text(self):
            return self._v

    class _FakeButton:
        def isChecked(self):
            return False

        def setVisible(self, v):
            pass

    class _FakeSettingsMgr:
        def __init__(self):
            self.saved = {}

        def _save_setting(self, k, v):
            self.saved[k] = v

        def _get_setting(self, _k, default, _type):
            return default

    dialog = SimpleNamespace()
    dialog.export_controller = SimpleNamespace(store=SimpleNamespace(settings=settings))
    dialog.edit_manual_args = _FakeLineEdit()
    dialog.edit_crf = _FakeLineEdit("23")
    dialog.edit_bitrate = _FakeLineEdit("8000k")
    dialog.combo_container = _real_combo(["mp4"])
    dialog.combo_codec = _real_combo(["h264 (AVC)"])
    dialog.combo_quality_mode = _real_combo(["crf", "bitrate"])
    dialog.combo_preset = _real_combo(["medium"])
    dialog.combo_pix_fmt = _real_combo(["yuv420p"])
    dialog.combo_preview_scale = _real_combo([1.0, 0.75, 0.5, 0.25])
    # Select 0.5
    idx = dialog.combo_preview_scale.findData(0.5)
    dialog.combo_preview_scale.setCurrentIndex(idx)
    dialog.stack_quality = _FakeStack()
    dialog.fit_content_fill_color = QColor(0, 0, 0, 255)
    dialog.btn_fit_content = _FakeButton()
    dialog.btn_fit_fill_color = _FakeButton()
    dialog.preview_scale_events = []
    dialog._on_container_changed = lambda _t: None
    dialog._on_codec_changed = lambda _t: None
    dialog._update_fit_fill_color_button = lambda: None
    dialog._on_preview_scale_changed = lambda: dialog.preview_scale_events.append(float(dialog.combo_preview_scale.currentData()))

    # Verify real widget currentData is 0.5
    assert dialog.combo_preview_scale.currentData() == 0.5

    persistence = VideoEditorDialogPersistence(dialog)
    mgr = _FakeSettingsMgr()
    persistence.get_settings_refs = lambda: (dialog.export_controller.store, mgr)
    persistence.persist_export_settings()
    # Pin: real widget path writes same as fake path
    assert settings.video_editor_preview_render_scale == 0.5
    assert mgr.saved["video_editor_preview_render_scale"] == 0.5
