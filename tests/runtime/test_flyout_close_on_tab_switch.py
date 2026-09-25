"""Wave W4 (modal-lifetime): unified list closes on tab switch.

Mirror of the toast discipline with opposite polarity — toasts persist and
repoint at the new tab's anchor (``sync_session_mode``); transient flyouts
are transient so they close. Covers the extended
``_dismiss_ordinary_flyouts_on_tab_change`` path:

- an open unified list picker is hidden by the tab-switch hook (including
  one the toolkit sweep cannot see because it was never registered);
- anchored overlay popups owned by the previous tab are hidden too;
- toasts are untouched by the hook (anchor never repointed, toast still up);
- anchors re-sync lazily on the next show (picker re-reads anchors at show
  time — the tab's ``show_flyout`` re-syncs first, exercised here at the
  picker seam);
- fail-open: missing attrs/refs never crash the switch.

Host-level only: no ``tabs.*`` tab internals (see
``test_root_tests_no_tab_internals_leak``).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from sli_ui_toolkit.managers import FlyoutManager

from shared_toolkit.ui.overlay_layer import OverlayLayer
from ui.presenters.main_window.workspace import (
    _dismiss_ordinary_flyouts_on_tab_change,
    on_workspace_tab_changed,
)
from ui.widgets.unified_list_picker import UnifiedListPicker


def _host_window():
    window = QWidget()
    window.setObjectName("MainWindow")
    window.resize(800, 600)
    # Production main windows always carry .presenter — the sanctioned
    # window resolver keys off it.
    window.presenter = SimpleNamespace()
    window.show()
    QApplication.processEvents()
    return window


def _anchors(window):
    left = QWidget(window)
    left.setObjectName("combo_left")
    left.setGeometry(10, 10, 120, 30)
    right = QWidget(window)
    right.setObjectName("combo_right")
    right.setGeometry(140, 10, 120, 30)
    return left, right


def _open_picker(window, left, right):
    flyout = UnifiedListPicker.create_double_list(
        window, left, right, left_items=["a.png", "b.png"], right_items=["c.png"]
    )
    flyout.showAsSingle(1, left)
    QApplication.processEvents()
    assert flyout.isVisible()
    return flyout


def test_tab_switch_hook_hides_open_unified_list(qapp):
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)

    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()

    assert not flyout.isVisible()


def test_tab_switch_hook_hides_unregistered_unified_list(qapp):
    """A picker the toolkit sweep cannot see still closes (explicit hide)."""
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)
    FlyoutManager.get_instance().unregister_flyout(flyout)

    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()

    assert not flyout.isVisible()


def test_tab_switch_hook_hides_presenter_owned_unified_list(qapp):
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)
    presenter = SimpleNamespace(
        ui_manager=SimpleNamespace(unified_flyout=flyout),
        main_window_app=window,
    )

    _dismiss_ordinary_flyouts_on_tab_change(presenter)
    QApplication.processEvents()

    assert not flyout.isVisible()


def test_tab_switch_hook_hides_anchored_overlay_popup(qapp):
    window = _host_window()
    left, _right = _anchors(window)
    layer = OverlayLayer(window)
    window.overlay_layer = layer
    layer.show_popup("probe", left, text="hi", size=QSize(120, 40), timeout_ms=0)
    QApplication.processEvents()
    popup = layer._value_popups["probe"]
    assert popup.isVisible()

    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()

    assert not popup.isVisible()


def test_tab_switch_hook_leaves_toasts_alone(qapp):
    """Toasts persist: anchor never repointed, toast still visible."""
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)
    toast_manager = SimpleNamespace(set_anchor=Mock())
    window.toast_manager = toast_manager
    toast = QLabel("saving…", parent=window)
    toast.setObjectName("ToastProbe")
    toast.show()
    QApplication.processEvents()
    assert toast.isVisible()

    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()

    assert not flyout.isVisible()
    toast_manager.set_anchor.assert_not_called()
    assert toast.isVisible()


def test_anchors_resync_on_next_show(qapp):
    """After a tab-switch hide, the next show uses current anchors."""
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)

    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()
    assert not flyout.isVisible()

    # What the tab's show_flyout does first: re-read the current combos.
    new_left = QWidget(window)
    new_left.setObjectName("combo_left_new")
    new_left.setGeometry(10, 60, 120, 30)
    new_right = QWidget(window)
    new_right.setObjectName("combo_right_new")
    new_right.setGeometry(140, 60, 120, 30)
    flyout.set_list_anchors(new_left, new_right)

    flyout.showAsSingle(1, new_left)
    QApplication.processEvents()

    assert flyout.isVisible()
    assert flyout.anchor_for_list(1) is new_left
    assert flyout.anchor_for_list(2) is new_right


def test_tab_switch_via_workspace_tab_changed_hook(qapp):
    """The real tab-change entry point dismisses before switching."""
    window = _host_window()
    left, right = _anchors(window)
    flyout = _open_picker(window, left, right)
    tabs = Mock()
    tabs.tabData = Mock(return_value="session-1")
    switch = Mock()
    presenter = SimpleNamespace(
        ui=SimpleNamespace(workspace_tabs=tabs),
        main_controller=SimpleNamespace(
            workspace=SimpleNamespace(switch_workspace_session=switch)
        ),
    )

    on_workspace_tab_changed(presenter, 0)
    QApplication.processEvents()

    assert not flyout.isVisible()
    switch.assert_called_once_with("session-1")


def test_tab_switch_hook_fail_open_on_missing_refs(qapp):
    # Nothing open, no presenter at all.
    _dismiss_ordinary_flyouts_on_tab_change()
    # Presenter double with no ui_manager.
    _dismiss_ordinary_flyouts_on_tab_change(SimpleNamespace())
    # ui_manager double with no unified_flyout attr.
    _dismiss_ordinary_flyouts_on_tab_change(
        SimpleNamespace(ui_manager=SimpleNamespace())
    )
    # Unified ref without QWidget API.
    _dismiss_ordinary_flyouts_on_tab_change(
        SimpleNamespace(ui_manager=SimpleNamespace(unified_flyout=SimpleNamespace()))
    )
    # Overlay layer whose hide explodes.
    window = _host_window()

    def _boom():
        raise RuntimeError("gone")

    window.overlay_layer = SimpleNamespace(hide_all_popups=_boom)
    _dismiss_ordinary_flyouts_on_tab_change(SimpleNamespace(main_window_app=window))
    # Second sweep is a no-op, still no crash.
    _dismiss_ordinary_flyouts_on_tab_change()
    QApplication.processEvents()
