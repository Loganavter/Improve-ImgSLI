"""image_compare's canvas surface follows theme background changes.

Covers apply_image_canvas_appearance, the tab-owned counterpart of the
host's MainWindowAppearance.update_image_label_background (see
tests/plugins/test_main_window_canvas_theme_background.py for the
self-themed startup surfaces).
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


def test_apply_image_canvas_appearance_paints_label_and_container():
    app = _app()
    color = QColor("#123456")
    image_label = QWidget()
    container = QWidget()
    placeholder = StartupPlaceholder(container, target_widget=image_label)
    window = SimpleNamespace(
        theme_manager=_ThemeManager(color),
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
    assert container.autoFillBackground() is True

    placeholder.deleteLater()
    container.deleteLater()
    image_label.deleteLater()
    app.processEvents()


def test_startup_placeholder_tracks_theme_token():
    app = _app()
    color = QColor("#123456")
    theme_manager = _ThemeManager(color)
    parent = QWidget()
    placeholder = StartupPlaceholder(parent, target_widget=None)
    placeholder._theme_manager = theme_manager
    placeholder.on_theme_changed()

    assert placeholder._bg_color == color

    placeholder.deleteLater()
    parent.deleteLater()
    app.processEvents()
