"""FlyoutSurfaceWidget paints the flyout tokens — the retired
``QWidget#FlyoutWidget`` QSS rules (base.qss / widgets.qss) replaced by
code. Also covers the picker-side scroll-area transparency pins."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QScrollArea,
    QWidget,
)

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from sli_ui_toolkit.theme import ThemeManager
from ui.widgets.unified_list_picker.surface import (
    FlyoutSurfaceWidget,
    pin_scroll_area_transparency,
)


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


def _pixel(widget, x, y):
    return widget.grab().toImage().pixelColor(x, y)


def _translucent_host(surface):
    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    host.resize(320, 220)
    surface.setParent(host)
    surface.setGeometry(20, 20, 280, 180)
    host.show()
    return host


def _rgb(color) -> tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def test_container_role_paints_flyout_background(qapp, theme_manager):
    surf = FlyoutSurfaceWidget()
    surf.setProperty("surfaceRole", "container")
    host = _translucent_host(surf)

    center = _pixel(host, 160, 110)
    expected = QColor(theme_manager.get_color("flyout.background"))
    assert _rgb(center) == _rgb(expected)
    assert center.alpha() == 255
    # Rounded corner: the arc must stay transparent (the picker's shadow
    # pass shows through), not square.
    assert _pixel(host, 20, 20).alpha() == 0


def test_border_stroke_painted(qapp, theme_manager):
    surf = FlyoutSurfaceWidget()
    surf.setProperty("surfaceRole", "container")
    host = _translucent_host(surf)

    border_row = _pixel(host, 160, 20)  # 1px stroke at the top edge
    center = _pixel(host, 160, 110)
    assert border_row != center
    assert border_row.alpha() == 255


def test_transparent_role_paints_nothing(qapp, theme_manager):
    surf = FlyoutSurfaceWidget()
    surf.setProperty("surfaceRole", "transparent")
    host = _translucent_host(surf)

    assert _pixel(host, 160, 110).alpha() == 0


def test_property_change_repaints(qapp, theme_manager):
    surf = FlyoutSurfaceWidget()
    surf.setProperty("surfaceRole", "container")
    host = _translucent_host(surf)
    assert _pixel(host, 160, 110).alpha() == 255

    # No explicit update() — the DynamicPropertyChange handler repaints.
    surf.setProperty("surfaceRole", "transparent")
    assert _pixel(host, 160, 110).alpha() == 0


def test_retints_on_theme_change(qapp, theme_manager):
    surf = FlyoutSurfaceWidget()
    surf.setProperty("surfaceRole", "container")
    host = _translucent_host(surf)

    theme_manager.set_theme("light")
    center = _pixel(host, 160, 110)
    expected = QColor(theme_manager.get_color("flyout.background"))
    assert _rgb(center) == _rgb(expected)


def test_pin_scroll_area_transparency(qapp):
    root = QWidget()
    area = QScrollArea(root)
    content = QWidget()
    area.setWidget(content)
    assert content.autoFillBackground() or area.viewport().autoFillBackground()

    pin_scroll_area_transparency(root)
    assert area.autoFillBackground() is False
    assert area.viewport().autoFillBackground() is False
    assert content.autoFillBackground() is False


def test_picker_container_wiring(qapp, theme_manager):
    from ui.widgets.unified_list_picker import UnifiedListPicker

    host = QWidget()
    host.resize(600, 400)
    anchor_left = QWidget(host)
    anchor_left.setGeometry(50, 200, 200, 34)
    anchor_right = QWidget(host)
    anchor_right.setGeometry(350, 200, 200, 34)

    picker = UnifiedListPicker.create_double_list(
        host,
        anchor_left,
        anchor_right,
        left_items=["Alpha", "Beta", "Gamma"],
        right_items=["One", "Two"],
    )
    picker.set_list_anchors(anchor_left, anchor_right)
    picker.resize(300, 260)
    picker._apply_container_geometry()
    picker._position_panels_for_single()

    container = picker.container_widget
    assert isinstance(container, FlyoutSurfaceWidget)
    assert container.objectName() == "FlyoutWidget"
    assert container.property("surfaceRole") == "container"
    assert not container.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    areas = container.findChildren(QAbstractScrollArea)
    assert len(areas) == 2
    assert all(not area.autoFillBackground() for area in areas)
    assert all(not area.viewport().autoFillBackground() for area in areas)

    picker.panel_left.hide()
    picker.panel_right.hide()
    host.show()
    picker.show()
    img = container.grab().toImage()
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    expected = QColor(theme_manager.get_color("flyout.background"))
    assert _rgb(center) == _rgb(expected)

    picker.close()
    picker.deleteLater()
    host.close()
    host.deleteLater()