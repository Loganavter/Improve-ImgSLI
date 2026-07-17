"""Modal rename/properties must not dismiss the image-list flyout."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QDialog, QWidget

from ui.managers.transient_ui_parts.closing import (
    PopupClosingController,
    _modal_dialog_blocks_transient_hide,
)


def test_modal_dialog_blocks_transient_hide_flag():
    host = SimpleNamespace(_is_modal_active=True)
    assert _modal_dialog_blocks_transient_hide(host) is True


def test_modal_dialog_blocks_transient_hide_via_active_modal(qapp):
    host = SimpleNamespace(_is_modal_active=False)
    dialog = QDialog()
    dialog.setModal(True)
    dialog.show()
    qapp.processEvents()
    try:
        # exec() isn't required — Qt reports an open modal via activeModalWidget
        # only after exec in some platforms; window()+isModal still counts.
        assert _modal_dialog_blocks_transient_hide(host, dialog) is True
    finally:
        dialog.close()
        dialog.deleteLater()


def test_focus_to_modal_does_not_schedule_flyout_hide(qapp, monkeypatch):
    parent = QWidget()
    parent.show()
    qapp.processEvents()

    host = SimpleNamespace(
        parent_widget=parent,
        _is_modal_active=False,
        _interp_popup_open=False,
        _interp_flyout=None,
        _font_popup_open=False,
        font_settings_flyout=None,
    )
    manager = SimpleNamespace(
        host=host,
        interpolation=None,
        font_settings=None,
    )

    controller = PopupClosingController.__new__(PopupClosingController)
    controller.manager = manager
    controller._tab_extension = SimpleNamespace(
        has_focus_inside=lambda w: w is parent,
        hide_same_window=lambda: (_ for _ in ()).throw(
            AssertionError("flyout must stay open while modal rename is up")
        ),
    )
    controller._hide_transient_scheduled = False

    dialog = QDialog(parent)
    dialog.setModal(True)
    dialog.show()
    qapp.processEvents()

    scheduled = []
    monkeypatch.setattr(
        "PySide6.QtCore.QTimer.singleShot",
        lambda _ms, fn: scheduled.append(fn),
    )

    controller.on_app_focus_changed(parent, dialog)
    assert scheduled == []

    dialog.close()
    dialog.deleteLater()
    parent.deleteLater()


def test_deactivate_hide_respects_modal_flag(qapp, monkeypatch):
    """WindowDeactivate while rename dialog is up must not close the list."""
    from ui.managers.ui_manager import UIManager

    parent = QWidget()
    parent.show()
    qapp.processEvents()

    # Minimal stub — only exercise _schedule_hide_transient_if_still_inactive.
    manager = UIManager.__new__(UIManager)
    manager.parent_widget = parent
    manager._is_modal_active = True
    manager._deactivate_hide_scheduled = False
    calls = []
    manager.transient = SimpleNamespace(
        hide_transient_same_window_ui=lambda **kw: calls.append(kw)
    )

    ran = []
    monkeypatch.setattr(
        "PySide6.QtCore.QTimer.singleShot",
        lambda _ms, fn: ran.append(fn) or fn(),
    )

    manager._schedule_hide_transient_if_still_inactive()
    assert calls == []

    parent.deleteLater()
