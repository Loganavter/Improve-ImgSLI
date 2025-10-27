"""
Theme Manager for shared toolkit.

This module provides a unified theme management system that is
project-agnostic. Each project should provide its own color palettes.
"""

import os
import copy
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

class ThemeManager(QObject):
    """
    Unified theme manager for shared toolkit.

    This class provides theme management functionality that works across
    different projects. Projects should register their palettes using
    register_palettes() method.
    """

    theme_changed = pyqtSignal()

    _instance: Optional['ThemeManager'] = None

    def __init__(self):
        super().__init__()
        self._current_theme = "light"
        self._light_palette = {}
        self._dark_palette = {}
        self._qss_template = ""
        self._qss_paths = []

    @classmethod
    def get_instance(cls) -> 'ThemeManager':
        """Get the singleton instance of ThemeManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_palettes(self, light_palette: Dict, dark_palette: Dict = None):
        """
        Register color palettes for the application.

        Args:
            light_palette: Dictionary mapping color keys to QColor objects for light theme
            dark_palette: Dictionary mapping color keys to QColor objects for dark theme (optional)
        """
        self._light_palette = copy.deepcopy(light_palette)
        if dark_palette:
            self._dark_palette = copy.deepcopy(dark_palette)
        else:
            self._dark_palette = copy.deepcopy(light_palette)

    def register_qss_path(self, qss_path: str):
        """
        Register a QSS file path to load styles from.

        Args:
            qss_path: Path to the QSS file
        """
        if os.path.exists(qss_path):
            self._qss_paths.append(qss_path)
            self._load_qss_template()
        else:
            pass

    def get_color(self, color_key: str) -> QColor:
        """
        Get a color from the current theme palette.

        Args:
            color_key: The key for the color in the palette

        Returns:
            QColor object for the requested color (always a fresh copy)
        """
        palette = self._dark_palette if self.is_dark() else self._light_palette
        value = palette.get(color_key)

        if isinstance(value, QColor):
            return QColor(value)
        if isinstance(value, str):
            return QColor(value)
        return QColor("#000000")

    def set_color(self, color_key: str, color: QColor):
        """
        Set a color in the current theme palette.

        Args:
            color_key: The key for the color in the palette
            color: The QColor to set
        """

        color_to_store = QColor(color) if isinstance(color, QColor) else QColor(str(color))
        if self.is_dark():
            self._dark_palette[color_key] = color_to_store
        else:
            self._light_palette[color_key] = color_to_store
        self._apply_theme()
        self.theme_changed.emit()

    def get_current_theme(self) -> str:
        """Get the name of the current theme."""
        return self._current_theme

    def is_dark(self) -> bool:
        """Check if current theme is dark."""
        return self._current_theme == "dark"

    def set_theme(self, theme_name: str, app=None):
        """
        Set the current theme.

        Args:
            theme_name: Name of the theme to set ("light", "dark", or "auto")
            app: QApplication instance (optional)
        """
        new_theme = "dark" if theme_name == "dark" else "light"

        if self._current_theme != new_theme:
            self._current_theme = new_theme

            if app and self._qss_template:
                self.apply_theme_to_app(app)
            else:
                self._apply_theme()
            self.theme_changed.emit()
        else:
            if not app.styleSheet():
                self.apply_theme_to_app(app)

    def _load_qss_template(self):
        """Load QSS template file from registered paths."""
        try:
            for qss_path in self._qss_paths:
                if os.path.exists(qss_path):
                    with open(qss_path, "r", encoding="utf-8") as f:
                        self._qss_template = f.read()
                    return

        except Exception as e:
            self._qss_template = ""

    def apply_theme_to_app(self, app):
        """Apply the current theme to the QApplication, including QSS styles."""
        palette_data = self._dark_palette if self.is_dark() else self._light_palette

        if not palette_data:
            return

        q_palette = QPalette()
        color_roles = {
            "Window": QPalette.ColorRole.Window,
            "WindowText": QPalette.ColorRole.WindowText,
            "Base": QPalette.ColorRole.Base,
            "AlternateBase": QPalette.ColorRole.AlternateBase,
            "ToolTipBase": QPalette.ColorRole.ToolTipBase,
            "ToolTipText": QPalette.ColorRole.ToolTipText,
            "Text": QPalette.ColorRole.Text,
            "Button": QPalette.ColorRole.Button,
            "ButtonText": QPalette.ColorRole.ButtonText,
            "BrightText": QPalette.ColorRole.BrightText,
            "Highlight": QPalette.ColorRole.Highlight,
            "HighlightedText": QPalette.ColorRole.HighlightedText,
        }

        for name, role in color_roles.items():
            if name in palette_data:

                color = QColor(palette_data[name])
                q_palette.setColor(role, color)

        app.setPalette(q_palette)

        processed_palette = palette_data.copy()
        if 'accent' in processed_palette:
            accent_color = QColor(processed_palette['accent'])
            hover_color = accent_color.lighter(115) if self.is_dark() else accent_color.darker(115)
            processed_palette['accent.hover'] = hover_color

        current_qss = self._qss_template
        sorted_keys = sorted(processed_palette.keys(), key=len, reverse=True)

        for key in sorted_keys:
            color = processed_palette[key]
            if isinstance(color, QColor):
                placeholder = f"@{key}"
                if placeholder in current_qss:
                    current_qss = current_qss.replace(placeholder, color.name(QColor.NameFormat.HexArgb))

        app.setStyleSheet("")
        QApplication.processEvents()
        app.setStyleSheet(current_qss)

        main_window = app.activeWindow()
        if main_window:
            main_window.style().unpolish(main_window)
            main_window.style().polish(main_window)
            main_window.update()

    def _apply_theme(self):
        """Apply the current theme to the application."""
        app = QApplication.instance()
        if app is None:
            return

        self.apply_theme_to_app(app)

    def apply_theme_to_dialog(self, dialog):
        """Apply theme to a specific dialog."""

        dialog.style().unpolish(dialog)
        dialog.style().polish(dialog)
        dialog.updateGeometry()
        dialog.update()
