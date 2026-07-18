"""Bottom name LineEdit Find Action contributions."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from core.actions.types import ActionTarget
from sli_ui_toolkit.widgets import Button, CustomLineEdit
from tabs.image_compare.actions import (
    _contribute_name_edit_actions,
    _ensure_name_edit_chrome,
    _focus_name_edit,
)
from ui.actions.registry import ActionRegistry


def test_name_edit_ensure_shows_edit_row(qtbot, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    edit_row = QWidget(host)
    edit_row.hide()
    edit = CustomLineEdit(host)
    edit.hide()
    file_btn = Button("settings", parent=host, toggle=True)
    file_btn.setChecked(False)
    text_btn = Button("settings", parent=host)
    text_btn.hide()

    shown: list[bool] = []

    def _toggle(checked: bool) -> None:
        shown.append(checked)
        edit_row.setVisible(checked)
        edit.setVisible(checked)

    widget = SimpleNamespace(
        edit_layout_widget=edit_row,
        edit_name1=edit,
        edit_name2=CustomLineEdit(host),
        btn_file_names=file_btn,
        btn_text_settings=text_btn,
        toggle_edit_layout_visibility=_toggle,
    )

    monkeypatch.setattr(
        "tabs.image_compare.actions._host_font_settings_controller",
        lambda: None,
    )
    _ensure_name_edit_chrome(widget)
    assert shown == [True]
    assert edit_row.isVisible()
    assert file_btn.isChecked()


def test_name_edit_actions_listed_while_hidden_and_run_shows(qtbot, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 200)
    host.show()
    qtbot.waitExposed(host)

    edit1 = CustomLineEdit(host)
    edit1.hide()
    edit2 = CustomLineEdit(host)
    edit2.hide()
    file_btn = Button("settings", parent=host, toggle=True)
    file_btn.setChecked(False)
    text_btn = Button("settings", parent=host)
    text_btn.hide()

    def _toggle(checked: bool) -> None:
        edit1.setVisible(checked)
        edit2.setVisible(checked)

    widget = SimpleNamespace(
        edit_name1=edit1,
        edit_name2=edit2,
        btn_file_names=file_btn,
        btn_text_settings=text_btn,
        toggle_edit_layout_visibility=_toggle,
    )

    monkeypatch.setattr(
        "tabs.image_compare.actions._host_font_settings_controller",
        lambda: None,
    )

    reg = ActionRegistry()
    _contribute_name_edit_actions(widget, reg)

    listed = reg.list_for(active_tab="image_compare", query="")
    listed_ids = {a.action_id for a in listed}
    assert "image_compare.rename_image1" in listed_ids
    assert "image_compare.rename_image2" in listed_ids

    action = next(a for a in listed if a.action_id == "image_compare.rename_image1")
    assert isinstance(action.target, ActionTarget)
    assert callable(action.target.ensure_visible)
    assert action.target.resolve_widget() is edit1

    assert callable(action.run)
    action.run()
    assert edit1.isVisible()


def test_focus_name_edit_selects_text(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    edit = CustomLineEdit(host)
    edit.setText("photo")
    edit.show()
    _focus_name_edit(edit)
    assert edit.selectedText() == "photo"
