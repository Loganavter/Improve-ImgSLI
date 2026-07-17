"""AppMessageDialog follows the active theme with explicit CSD."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor

from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations
from shared_toolkit.ui.message_dialog import AppMessageDialog, MessageKind


def test_app_message_dialog_has_csd_chrome(qapp):
    install_application_dialog_decorations(qapp)
    dialog = AppMessageDialog(
        kind=MessageKind.INFORMATION,
        title="Restart required",
        text="backend change",
    )
    qapp.processEvents()

    assert getattr(dialog, "_csd_paint_state", None) is not None
    assert getattr(dialog, "_csd_title_bar", None) is not None
    assert getattr(dialog, "_csd_bg_layer", None) is not None
    dialog.deleteLater()


def test_app_message_dialog_paints_light_window_body(qapp):
    from core.theme import LIGHT_THEME_PALETTE, DARK_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.register_qss_path("src/shared_toolkit/ui/resources/styles/base.qss")
    tm.set_theme("light", qapp)

    install_application_dialog_decorations(qapp)
    dialog = AppMessageDialog(
        kind=MessageKind.INFORMATION,
        title="Restart required",
        text="The render backend will change after restart.",
    )
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
    dialog.deleteLater()


def test_app_message_dialog_is_edge_resizable(qapp):
    from sli_ui_toolkit.ui.windows.frameless import _ResizeFilter

    dialog = AppMessageDialog(
        kind=MessageKind.INFORMATION,
        title="Info",
        text="Edge resize handles on alerts.",
    )
    qapp.processEvents()
    assert dialog.findChild(_ResizeFilter) is not None
    dialog.deleteLater()


def test_app_message_dialog_updates_paint_state_on_theme_change(qapp):
    from core.theme import LIGHT_THEME_PALETTE, DARK_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("light")

    dialog = AppMessageDialog(
        kind=MessageKind.WARNING,
        title="Error",
        text="boom",
    )
    expected = QColor(LIGHT_THEME_PALETTE["Window"])
    assert dialog._csd_paint_state["color"] == expected

    tm.set_theme("dark")
    qapp.processEvents()

    assert dialog._csd_paint_state["color"] == QColor(tm.get_color("Window"))
    dialog.deleteLater()
