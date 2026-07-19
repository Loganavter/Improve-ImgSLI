"""FlyoutManager must not wipe in-window flyouts for modal / Wayland focus handoff."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import QEvent, QTimer, Qt
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


class _AppStateProxy:
    """Real QApplication with overridden activate/modal probes for Windows CI.

    Patching ``applicationState`` / ``activeModalWidget`` on the Qt class is
    unreliable under Windows PySide6. ``FlyoutManager._maybe_close`` uses
    ``QApplication.instance()``, so we return a thin proxy for that call only.
    """

    def __init__(self, real: QApplication, *, state, modal_widget):
        self._real = real
        self._state = state
        self._modal_widget = modal_widget

    def applicationState(self):
        return self._state

    def activeModalWidget(self):
        return self._modal_widget

    def __getattr__(self, name):
        return getattr(self._real, name)


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
    proxy = _AppStateProxy(qapp, state=state, modal_widget=modal_widget)

    ran = []

    def _single_shot(_ms, fn):
        ran.append(fn)
        # Scope the instance swap to the deferred close body so pytest-qt
        # teardown still sees the real QApplication.
        with patch.object(QApplication, "instance", return_value=proxy):
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

    manager.unregister_flyout(flyout)
    flyout.deleteLater()
    dialog.deleteLater()
