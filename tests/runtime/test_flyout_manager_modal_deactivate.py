"""FlyoutManager must not wipe in-window flyouts for modal / Wayland focus handoff."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QDialog, QWidget
from sli_ui_toolkit.managers import FlyoutManager


class _VisibleFlyout(QWidget):
    flyout_group = "unified_list"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_calls = 0

    def hide(self):  # noqa: A003 — Qt API
        self.hide_calls += 1
        super().hide()


def _run_deactivate(
    manager,
    qapp,
    monkeypatch,
    *,
    application_active: bool,
    modal_widget=None,
):
    manager._deactivate_close_scheduled = False
    state = (
        Qt.ApplicationState.ApplicationActive
        if application_active
        else Qt.ApplicationState.ApplicationInactive
    )

    # FlyoutManager._maybe_close requires isinstance(app, QApplication), so
    # the probed methods must be overridden on the real instance rather than
    # swapped out via a duck-typed stand-in for QApplication.instance().
    monkeypatch.setattr(qapp, "applicationState", lambda: state)
    monkeypatch.setattr(qapp, "activeModalWidget", lambda: modal_widget)

    ran = []

    def _single_shot(_ms, fn):
        ran.append(fn)
        fn()

    monkeypatch.setattr(QTimer, "singleShot", _single_shot)

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

    try:
        _run_deactivate(manager, qapp, monkeypatch, application_active=True)
        assert flyout.hide_calls == 0
        assert flyout.isVisible()
    finally:
        manager.unregister_flyout(flyout)
        flyout.hide()
        flyout.close()
        flyout.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()


def test_flyout_manager_deactivate_closes_when_app_inactive(qapp, monkeypatch):
    from PySide6.QtCore import QEvent

    manager = FlyoutManager.get_instance()
    flyout = _VisibleFlyout()
    flyout.show()
    manager.register_flyout(flyout)
    manager._active_flyout = flyout
    manager._install_event_filter()

    try:
        _run_deactivate(manager, qapp, monkeypatch, application_active=False)
        assert flyout.hide_calls == 1
    finally:
        manager.unregister_flyout(flyout)
        flyout.hide()
        flyout.close()
        flyout.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()


def test_flyout_manager_deactivate_skips_when_modal_open(qapp, monkeypatch):
    from PySide6.QtCore import QEvent

    manager = FlyoutManager.get_instance()
    flyout = _VisibleFlyout()
    flyout.show()
    manager.register_flyout(flyout)
    manager._active_flyout = flyout
    manager._install_event_filter()

    dialog = QDialog()
    try:
        # App inactive + no activeWindow would previously close_all; modal must win.
        _run_deactivate(
            manager,
            qapp,
            monkeypatch,
            application_active=False,
            modal_widget=dialog,
        )
        assert flyout.hide_calls == 0
        assert flyout.isVisible()
    finally:
        manager.unregister_flyout(flyout)
        flyout.hide()
        flyout.close()
        flyout.deleteLater()
        dialog.hide()
        dialog.close()
        dialog.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()