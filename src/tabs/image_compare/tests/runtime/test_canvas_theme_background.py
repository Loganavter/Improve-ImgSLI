"""image_compare's canvas surface follows theme background changes.

Covers apply_image_canvas_appearance, the tab-owned counterpart of the
host's generic MainWindowAppearance.update_image_label_background (see
tests/plugins/test_main_window_canvas_theme_background.py for the
host-generic startup-placeholder/cover half).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_compare.ui.appearance import apply_image_canvas_appearance
from ui.widgets.startup_placeholder import StartupPlaceholder

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


class _ThemeManager:
    def __init__(self, color: QColor):
        self.color = color

    def get_color(self, _key: str) -> QColor:
        return QColor(self.color)


def test_apply_image_canvas_appearance_paints_label_container_and_placeholder():
    app = _app()
    color = QColor("#123456")
    image_label = QWidget()
    container = QWidget()
    startup_placeholder = QWidget()
    startup_cover = QWidget()
    placeholder = StartupPlaceholder(container, target_widget=image_label)
    window = SimpleNamespace(
        theme_manager=_ThemeManager(color),
        _startup_placeholder=startup_placeholder,
        _startup_cover=startup_cover,
        ui=SimpleNamespace(
            image_label=image_label,
            image_container_widget=container,
            image_startup_placeholder=placeholder,
        ),
        findChildren=lambda _cls: [],
    )

    apply_image_canvas_appearance(window)

    assert image_label.palette().color(QPalette.ColorRole.Window) == color
    assert image_label.palette().color(QPalette.ColorRole.Base) == color
    assert container.palette().color(QPalette.ColorRole.Window) == color
    assert container.palette().color(QPalette.ColorRole.Base) == color
    assert placeholder.palette().color(QPalette.ColorRole.Window) == color
    assert placeholder.palette().color(QPalette.ColorRole.Base) == color
    assert startup_placeholder.palette().color(QPalette.ColorRole.Window) == color
    assert startup_cover.palette().color(QPalette.ColorRole.Window) == color
    assert container.autoFillBackground() is True
    assert placeholder.autoFillBackground() is True

    placeholder.deleteLater()
    startup_cover.deleteLater()
    startup_placeholder.deleteLater()
    container.deleteLater()
    image_label.deleteLater()
    app.processEvents()
