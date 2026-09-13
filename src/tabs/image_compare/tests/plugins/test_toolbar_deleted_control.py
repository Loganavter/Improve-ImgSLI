"""Regression: deleted Qt controls must be skipped by construction.

A ValueSlider (or any toolbar control) whose C++ object was deleted by a
chrome rebuild keeps its Python wrapper alive on the widget, so a bare
``control.setEnabled(...)`` raises ``RuntimeError: ... already deleted``
— once per store emit (storm), freezing the whole availability fanout.
See also ``test_color_button_disconnects_store_when_destroyed``.

All three guarded sites delegate to the single mechanism in
``tabs.image_compare.canvas.live_handles`` (``LiveHandle`` /
``is_qt_alive`` / ``note_skipped_once``): toolbar availability + fanout
(``presenters/toolbar/state.py``), capture quiet-setter
(``canvas/features/capture/widget.py``), batcher flush
(``ui/presenters/ui_update_batcher.py``).

Phase P2 of plan-render-core-consolidation-2026-09-13.
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QPushButton, QWidget

from tabs.image_compare.canvas import live_handles
from tabs.image_compare.presenters.toolbar import state as toolbar_state


@pytest.fixture(autouse=True)
def _reset_skip_throttle(monkeypatch):
    """The once-per-key throttle is module-global — isolate every test."""
    monkeypatch.setattr(live_handles, "_last_skip_sig", None)


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


# --- live_handles registry itself -------------------------------------------


def test_live_handle_reports_live_and_dead(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    control = QPushButton(parent)
    handle = live_handles.LiveHandle(control, key="probe")
    assert handle.is_alive() is True
    assert live_handles.is_qt_alive(control) is True
    control.deleteLater()  # C++ gone, Python wrapper alive
    qtbot.wait(20)
    assert handle.is_alive() is False
    assert live_handles.is_qt_alive(control) is False


def test_live_handle_fail_open_without_shiboken(monkeypatch):
    """No shiboken (or an undecided answer) reports alive — the per-site
    try/except RuntimeError backstop still catches the race."""
    import sys

    monkeypatch.setitem(sys.modules, "shiboken6", None)
    assert live_handles.is_qt_alive(object()) is True
    assert live_handles.LiveHandle(object()).is_alive() is True


def test_skip_debug_throttled_once_per_key(caplog):
    with caplog.at_level("DEBUG", logger="ImproveImgSLI"):
        live_handles.note_skipped_once("k1", "skip %s", "k1")
        live_handles.note_skipped_once("k1", "skip %s", "k1")  # silent repeat
        assert caplog.text.count("skip k1") == 1
        live_handles.note_skipped_once("k2", "skip %s", "k2")  # new key logs
        assert "skip k2" in caplog.text


# --- batcher flush (shared host code) ----------------------------------------


class _BatcherPresenter(QObject):
    """QObject-backed: shiboken tracks it, so deleteLater() kills isValid."""

    def __init__(self, window):
        super().__init__()
        self.main_window_app = window
        self.calls = []

    def _do_update_combobox_displays(self):
        self.calls.append("combobox")


def _batcher_with(window):
    from ui.presenters.ui_update_batcher import UIUpdateBatcher

    presenter = _BatcherPresenter(window)
    batcher = UIUpdateBatcher(presenter)
    batcher._pending_updates = {"combobox"}
    return batcher, presenter


def test_batcher_flush_runs_when_handles_alive(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    window = QWidget(parent)
    batcher, presenter = _batcher_with(window)
    batcher._flush_updates()
    assert presenter.calls == ["combobox"]


def test_batcher_flush_skips_deleted_window(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    window = QWidget(parent)
    batcher, presenter = _batcher_with(window)
    window.deleteLater()  # C++ gone, Python wrapper alive
    qtbot.wait(20)
    batcher._flush_updates()  # must not raise, must not touch the presenter
    assert presenter.calls == []


def test_batcher_flush_skips_deleted_presenter(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    window = QWidget(parent)
    batcher, presenter = _batcher_with(window)
    presenter.deleteLater()  # C++ gone, Python wrapper alive
    qtbot.wait(20)
    batcher._flush_updates()  # must not raise
    assert presenter.calls == []
