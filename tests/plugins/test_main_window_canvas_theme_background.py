"""Generic main-window startup surfaces follow theme background changes.

Image-canvas-specific painting (image_label/container/placeholder) is owned
by each tab's ``apply_appearance`` hook and tested there — see
tabs/image_compare/tests/runtime/test_canvas_theme_background.py — since
``update_image_label_background`` only reaches ``window.ui`` widgets via
``registry.apply_appearance(window)``, which is a no-op without a real
``_tab_registry``.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from ui.main_window.appearance import MainWindowAppearance

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


def test_canvas_theme_background_updates_startup_placeholder_and_cover():
    app = _app()
    color = QColor("#123456")
    startup_placeholder = QWidget()
    startup_cover = QWidget()
    window = SimpleNamespace(
        theme_manager=_ThemeManager(color),
        _startup_placeholder=startup_placeholder,
        _startup_cover=startup_cover,
        ui=None,
    )

    MainWindowAppearance(window).update_image_label_background()

    assert startup_placeholder.palette().color(QPalette.ColorRole.Window) == color
    assert startup_cover.palette().color(QPalette.ColorRole.Window) == color

    startup_cover.deleteLater()
    startup_placeholder.deleteLater()
    app.processEvents()
