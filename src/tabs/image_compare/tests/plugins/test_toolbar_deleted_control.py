"""Regression: toolbar availability sync must skip shiboken-deleted controls.

A ValueSlider (or any toolbar control) whose C++ object was deleted by a
chrome rebuild keeps its Python wrapper alive on the widget, so the
``hasattr(control, "setEnabled")`` guard in ``state.py`` passes and the
bare ``control.setEnabled(...)`` raises ``RuntimeError: ... already
deleted`` — once per store emit (storm), freezing the whole availability
fanout. See also ``test_color_button_disconnects_store_when_destroyed``.
"""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QPushButton, QWidget

from tabs.image_compare.presenters.toolbar import state as toolbar_state


@pytest.fixture()
def presenter(qtbot, monkeypatch):
    monkeypatch.setattr(
        toolbar_state,
        "registry",
        lambda: SimpleNamespace(get_feature_toolbar_binding=lambda cid: object()),
    )
    parent = QWidget()
    qtbot.addWidget(parent)
    live = QPushButton(parent)
    dead = QPushButton(parent)
    widget = SimpleNamespace(btn_orientation=live, slider_size=dead)
    stub = SimpleNamespace(widget=widget)
    # NOTE: keep `parent` referenced — qtbot does not own it, and losing the
    # last ref deletes the C++ children out from under the test.
    return stub, live, dead, parent


def test_availability_skips_deleted_control(qtbot, caplog, presenter):
    stub, live, dead, _parent = presenter
    dead.deleteLater()  # C++ gone, Python wrapper alive (the storm shape)
    qtbot.wait(20)
    with caplog.at_level("DEBUG", logger="ImproveImgSLI"):
        toolbar_state._update_canvas_feature_control_availability(stub)  # must not raise
    assert live.isEnabled() is True
    assert "slider_size" in caplog.text


def test_availability_syncs_all_live_controls(qtbot, presenter):
    stub, live, dead, _parent = presenter
    toolbar_state._update_canvas_feature_control_availability(stub)
    assert live.isEnabled() is True
    assert dead.isEnabled() is True
