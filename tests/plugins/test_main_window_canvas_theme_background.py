"""Main-window canvas surface follows theme background changes."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from ui.main_window.appearance import MainWindowAppearance
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


def test_canvas_theme_background_updates_canvas_container_and_placeholder():
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
    )

    MainWindowAppearance(window).update_image_label_background()

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
