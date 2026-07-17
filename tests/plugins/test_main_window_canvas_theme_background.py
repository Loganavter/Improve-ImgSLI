"""Generic main-window startup surfaces self-repaint on theme change.

Startup placeholder/cover widgets are ThemedSurface instances that subscribe
to theme_changed directly. MainWindowAppearance only forwards to tab
apply_appearance hooks for canvas-specific surfaces.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from ui.widgets.themed_surface import ThemedSurface

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


def test_themed_surface_repaints_on_theme_change():
    app = _app()
    first = QColor("#123456")
    second = QColor("#abcdef")
    theme_manager = _ThemeManager(first)
    surface = ThemedSurface()

    surface._theme_manager = theme_manager
    surface.on_theme_changed()

    assert surface._bg_color == first

    theme_manager.color = second
    surface.on_theme_changed()

    assert surface._bg_color == second

    surface.deleteLater()
    app.processEvents()
