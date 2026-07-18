"""Mode picker popup policy tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Button, SimpleOptionsFlyout
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


def test_mode_picker_click_opens_options_flyout(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(20, 20)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("RGB", "rgb"), ("SSIM", "ssim")])
    picker.set_current("rgb")

    selected: list[object] = []
    picker.selected.connect(selected.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait(50)

    assert picker._flyout is not None
    assert isinstance(picker._flyout, SimpleOptionsFlyout)
    assert picker._flyout.isVisible()

    picker._on_item_chosen(1)
    assert selected == ["ssim"]
    assert picker._current == "ssim"


def test_mode_picker_opens_left_aligned_under_button(qtbot, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(40, 40)
    button.resize(36, 36)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("RGB", "rgb"), ("R", "r")])
    picker.set_current("rgb")

    calls: list[dict] = []

    def _capture(anchor, anchor_point="bottom-center", flyout_point="top-center", **kwargs):
        calls.append(
            {
                "anchor": anchor,
                "anchor_point": anchor_point,
                "flyout_point": flyout_point,
                "offset": kwargs.get("offset"),
                "animation": kwargs.get("animation"),
                "animation_axis": kwargs.get("animation_axis"),
            }
        )

    # Force create, then stub placement so we assert alignment without overlay geometry.
    flyout = picker._ensure_flyout()
    assert flyout is not None
    monkeypatch.setattr(flyout, "show_aligned", _capture)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait(20)

    assert len(calls) == 1
    assert calls[0]["anchor"] is button
    assert calls[0]["anchor_point"] == "bottom-left"
    assert calls[0]["flyout_point"] == "top-left"
    assert calls[0]["offset"] == 2
    assert calls[0]["animation"] == "slide"
    assert calls[0]["animation_axis"] == "vertical"


def test_mode_picker_choose_data_emits_and_hides(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(20, 20)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("RGB", "rgb"), ("SSIM", "ssim")])
    picker.set_current("rgb")

    selected: list[object] = []
    picker.selected.connect(selected.append)

    picker.open()
    assert picker._flyout is not None
    assert picker._flyout.isVisible()
    assert picker.row_widget(1) is not None

    picker.choose_data("ssim")
    assert selected == ["ssim"]
    assert picker._current == "ssim"
    assert not picker._flyout.isVisible()

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(40, 40)
    button.resize(36, 36)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("RGB", "rgb"), ("R", "r"), ("SSIM", "ssim")])
    picker.set_current("rgb")

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait(50)

    flyout = picker._flyout
    assert flyout is not None
    assert flyout.isVisible()
    # Opaque panel tracks the longest label instead of a fixed floor.
    longest = max(
        flyout._rows_layout.itemAt(i).widget().label.sizeHint().width()
        for i in range(3)
    )
    assert flyout.container.width() <= longest + 28
    assert flyout.width() < 180
