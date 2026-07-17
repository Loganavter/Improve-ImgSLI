"""FlyoutManager must not wipe in-window flyouts for modal / Wayland focus handoff."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from sli_ui_toolkit.managers import FlyoutManager


class _VisibleFlyout(QWidget):
    flyout_group = "unified_list"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_calls = 0

    def hide(self):  # noqa: A003 — Qt API
        self.hide_calls += 1
        super().hide()


def _run_deactivate(manager, qapp, monkeypatch, *, application_active: bool):
    manager._deactivate_close_scheduled = False
    monkeypatch.setattr(
        QApplication,
        "applicationState",
        lambda _self=None: (
            Qt.ApplicationState.ApplicationActive
            if application_active
            else Qt.ApplicationState.ApplicationInactive
        ),
    )
    ran = []
    monkeypatch.setattr(
        "PySide6.QtCore.QTimer.singleShot",
        lambda _ms, fn: ran.append(fn) or fn(),
    )
    event = QEvent(QEvent.Type.WindowDeactivate)
    manager.eventFilter(qapp, event)
    assert ran


def test_flyout_manager_deactivate_skips_when_app_active(qapp, monkeypatch):
    manager = FlyoutManager.get_instance()
    flyout = _VisibleFlyout()
    flyout.show()
    manager.register_flyout(flyout)
    manager._active_flyout = flyout
    manager._install_event_filter()

    _run_deactivate(manager, qapp, monkeypatch, application_active=True)
    assert flyout.hide_calls == 0
    assert flyout.isVisible()

    manager.unregister_flyout(flyout)
    flyout.deleteLater()


def test_flyout_manager_deactivate_closes_when_app_inactive(qapp, monkeypatch):
    manager = FlyoutManager.get_instance()
    flyout = _VisibleFlyout()
    flyout.show()
    manager.register_flyout(flyout)
    manager._active_flyout = flyout
    manager._install_event_filter()

    monkeypatch.setattr(QApplication, "activeModalWidget", lambda _self=None: None)
    _run_deactivate(manager, qapp, monkeypatch, application_active=False)
    assert flyout.hide_calls == 1

    manager.unregister_flyout(flyout)
    flyout.deleteLater()


def test_flyout_manager_deactivate_skips_when_modal_open(qapp, monkeypatch):
    manager = FlyoutManager.get_instance()
    flyout = _VisibleFlyout()
    flyout.show()
    manager.register_flyout(flyout)
    manager._active_flyout = flyout
    manager._install_event_filter()

    dialog = QDialog()
    monkeypatch.setattr(QApplication, "activeModalWidget", lambda _self=None: dialog)
    # App inactive + no activeWindow would previously close_all; modal must win.
    _run_deactivate(manager, qapp, monkeypatch, application_active=False)
    assert flyout.hide_calls == 0
    assert flyout.isVisible()

    manager.unregister_flyout(flyout)
    flyout.deleteLater()
    dialog.deleteLater()
