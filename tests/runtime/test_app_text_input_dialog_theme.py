"""AppTextInputDialog follows the same CSD path as AppMessageDialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor

from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations
from shared_toolkit.ui.text_input_dialog import AppTextInputDialog


def test_app_text_input_dialog_has_csd_chrome(qapp):
    from PySide6.QtCore import QEvent

    install_application_dialog_decorations(qapp)
    dialog = AppTextInputDialog(
        title="Rename Tab",
        prompt="Name",
        text="Tab 1",
    )
    try:
        qapp.processEvents()

        assert getattr(dialog, "_csd_paint_state", None) is not None
        assert getattr(dialog, "_csd_title_bar", None) is not None
        assert getattr(dialog, "_csd_bg_layer", None) is not None
    finally:
        dialog.hide()
        dialog.close()
        qapp.processEvents()
        dialog.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_app_text_input_dialog_is_edge_resizable(qapp):
    from PySide6.QtCore import QEvent
    from sli_ui_toolkit.ui.windows.frameless import _ResizeFilter

    dialog = AppTextInputDialog(title="Rename", prompt="Name", text="x")
    try:
        qapp.processEvents()
        assert dialog.findChild(_ResizeFilter) is not None
    finally:
        dialog.hide()
        dialog.close()
        qapp.processEvents()
        dialog.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_app_text_input_dialog_paints_light_window_body(qapp):
    from PySide6.QtCore import QEvent
    from core.theme import LIGHT_THEME_PALETTE, DARK_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.register_qss_path("src/shared_toolkit/ui/resources/styles/base.qss")
    tm.set_theme("light", qapp)

    install_application_dialog_decorations(qapp)
    dialog = AppTextInputDialog(
        title="Rename Tab",
        prompt="Name",
        text="Tab 1",
    )
    try:
        dialog.show()
        qapp.processEvents()

        img = dialog.grab().toImage()
        w, h = img.width(), img.height()
        assert w > 0 and h > 0
        body = img.pixelColor(w // 2, (h * 2) // 3)
        expected = QColor(LIGHT_THEME_PALETTE["Window"])
        assert body.red() == expected.red()
        assert body.green() == expected.green()
        assert body.blue() == expected.blue()
    finally:
        dialog.hide()
        dialog.close()
        qapp.processEvents()
        dialog.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
