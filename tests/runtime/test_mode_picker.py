"""Mode picker popup policy tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Button
from shared_toolkit.ui.mode_picker import ModePicker


def test_mode_picker_tracks_actions_and_emits_selected(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    picker = ModePicker.attach(button, id_prefix="test_mode")
    picker.set_actions([("RGB", "rgb"), ("SSIM", "ssim")])
    picker.set_current("rgb")

    selected: list[object] = []
    picker.selected.connect(selected.append)
    picker.selected.emit("ssim")

    assert selected == ["ssim"]


def test_mode_picker_cycle_next_wraps(qtbot):
    host = QWidget()
    qtbot.addWidget(host)

    button = Button("settings", parent=host)
    picker = ModePicker.attach(button)
    picker.set_actions([("RGB", "RGB"), ("R", "R"), ("G", "G")])
    picker.set_current("RGB")

    selected: list[object] = []
    picker.selected.connect(selected.append)

    picker.cycle_next()
    picker.cycle_next()
    picker.cycle_next()

    assert selected == ["R", "G", "RGB"]
