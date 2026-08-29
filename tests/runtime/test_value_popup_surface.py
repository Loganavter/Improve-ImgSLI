"""Value popup surface: ``_PopupBubble`` paints the flyout tokens itself —
the retired ``#ValuePopupContainer`` QSS rule (base.qss) replaced by code."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from shared_toolkit.ui.overlay_layer import _PopupBubble
from sli_ui_toolkit.theme import ThemeManager


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def theme_manager(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("dark")
    yield tm


def _make_popup(theme_manager, host):
    popup = _PopupBubble(host)
    popup.set_content(text="42")
    popup.move(50, 50)
    popup.show()
    return popup


def _rgb(color) -> tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def test_popup_center_is_flyout_background(qapp, theme_manager):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    popup = _make_popup(theme_manager, host)

    img = popup.grab().toImage()
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    expected = QColor(theme_manager.get_color("flyout.background"))
    assert _rgb(center) == _rgb(expected)
    assert center.alpha() == 255


def test_popup_container_has_no_styled_background(qapp, theme_manager):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    popup = _make_popup(theme_manager, host)

    assert not popup.container.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def test_popup_retints_on_theme_change(qapp, theme_manager):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    popup = _make_popup(theme_manager, host)

    theme_manager.set_theme("light")
    img = popup.grab().toImage()
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    expected = QColor(theme_manager.get_color("flyout.background"))
    assert _rgb(center) == _rgb(expected)