"""ModePicker / SimpleOptionsFlyout Find Action contributions."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from core.actions.types import ActionTarget
from sli_ui_toolkit.widgets import Button
from shared_toolkit.ui.mode_picker import ModePicker
from ui.actions.flyout_contribute import (
    SimpleOptionAction,
    contribute_simple_options_actions,
)
from ui.actions.registry import ActionRegistry


def test_simple_options_actions_listed_while_flyout_closed(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(20, 20)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("Off", "off"), ("Highlight", "highlight"), ("SSIM", "ssim")])
    picker.set_current("off")

    reg = ActionRegistry()
    ids = contribute_simple_options_actions(
        picker,
        options=(
            SimpleOptionAction("off", "image_compare.action.diff_off", "off"),
            SimpleOptionAction(
                "highlight",
                "image_compare.action.diff_highlight",
                "highlight",
                search_terms=("highlight",),
            ),
            SimpleOptionAction(
                "ssim",
                "image_compare.action.diff_ssim",
                "ssim",
                search_terms=("ssim",),
            ),
        ),
        prefix="image_compare.diff_mode.",
        owner_tab="image_compare",
        topic="analysis",
        breadcrumb=("toolbar", "analysis", "diff_mode"),
        registry=reg,
    )
    assert "image_compare.diff_mode.ssim" in ids
    assert "image_compare.diff_mode.highlight" in ids

    listed = reg.list_for(active_tab="image_compare", query="")
    listed_ids = {a.action_id for a in listed}
    assert "image_compare.diff_mode.ssim" in listed_ids

    ssim = next(a for a in listed if a.action_id == "image_compare.diff_mode.ssim")
    assert isinstance(ssim.target, ActionTarget)
    assert callable(ssim.target.ensure_visible)
    assert callable(ssim.target.resolve_widget)

    ssim.target.ensure_visible()
    assert picker._flyout is not None
    assert picker._flyout.isVisible()
    assert ssim.target.resolve_widget() is picker.row_widget(2)


def test_simple_options_run_applies_data_without_requiring_open(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    picker = ModePicker.attach(button)
    picker.set_actions([("Off", "off"), ("SSIM", "ssim")])
    picker.set_current("off")

    selected: list[object] = []
    picker.selected.connect(selected.append)

    reg = ActionRegistry()
    contribute_simple_options_actions(
        picker,
        options=(
            SimpleOptionAction("ssim", "image_compare.action.diff_ssim", "ssim"),
        ),
        prefix="probe.diff.",
        owner_tab="image_compare",
        topic="analysis",
        breadcrumb=("toolbar",),
        registry=reg,
    )
    action = reg.get("probe.diff.ssim")
    assert action is not None and callable(action.run)
    action.run()
    assert selected == ["ssim"]
    assert picker._current == "ssim"


def test_mode_picker_open_does_not_toggle_close(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()
    qtbot.waitExposed(host)

    button = Button("settings", parent=host)
    button.move(20, 20)
    button.show()
    picker = ModePicker.attach(button)
    picker.set_actions([("A", "a"), ("B", "b")])
    picker.set_current("a")

    flyout = picker.open()
    assert flyout is not None
    assert flyout.isVisible()
    again = picker.open()
    assert again is flyout
    assert flyout.isVisible()
