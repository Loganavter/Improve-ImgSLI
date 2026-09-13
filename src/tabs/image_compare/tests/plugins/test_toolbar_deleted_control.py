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


def test_capture_sync_skips_deleted_slider(qtbot, monkeypatch):
    """Same storm one level down: capture's own quiet-setter must survive
    a shiboken-deleted slider (production: binding.sync_state ->
    _sync_capture_toolbar_state -> slider.value() RuntimeError per emit)."""
    from PySide6.QtWidgets import QSlider

    from tabs.image_compare.canvas.features.capture import widget as capture_widget

    monkeypatch.setattr(capture_widget, "_capture_size_from_view_state", lambda vs: 0.5)
    parent = QWidget()
    qtbot.addWidget(parent)
    slider = QSlider(parent)
    store = SimpleNamespace(viewport=SimpleNamespace(view_state=object()))
    stub = SimpleNamespace(widget=SimpleNamespace(slider_capture=slider), store=store)
    capture_widget._sync_capture_toolbar_state(stub)  # live: must not raise
    slider.deleteLater()  # C++ gone, Python wrapper alive
    qtbot.wait(20)
    capture_widget._sync_capture_toolbar_state(stub)  # dead: must not raise


def test_bindings_fanout_survives_one_bad_feature(qtbot, monkeypatch, caplog):
    """One feature's stale refs must not take down the whole bindings loop."""
    from PySide6.QtWidgets import QPushButton

    calls = []
    bad = SimpleNamespace(
        control_id="bad.feature",
        sync_state=lambda presenter: (_ for _ in ()).throw(
            RuntimeError("libshiboken: Internal C++ object already deleted.")
        ),
    )
    good = SimpleNamespace(
        control_id="good.feature",
        sync_state=lambda presenter: calls.append(1),
    )
    monkeypatch.setattr(
        toolbar_state,
        "registry",
        lambda: SimpleNamespace(
            get_feature_toolbar_binding=lambda cid: None,
            get_feature_toolbar_bindings=lambda: (bad, good),
        ),
    )
    parent = QWidget()
    qtbot.addWidget(parent)
    widget = SimpleNamespace(
        btn_file_names=None,
        slider_speed=None,
        image_label=None,
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(include_file_names_in_saved=False),
            view_state=SimpleNamespace(movement_speed_per_sec=1.0),
        ),
        settings=SimpleNamespace(current_language="en"),
    )
    stub = SimpleNamespace(widget=widget, store=store)
    with caplog.at_level("DEBUG", logger="ImproveImgSLI"):
        toolbar_state.update_toolbar_states(stub)  # must not raise
    assert calls == [1]
    assert "bad.feature" in caplog.text
