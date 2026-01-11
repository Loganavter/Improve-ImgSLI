

import copy
import logging
import os
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

theme_logger = logging.getLogger("ThemeManager")

class ThemeManager(QObject):

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
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_palettes(self, light_palette: Dict, dark_palette: Dict = None):
        self._light_palette = copy.deepcopy(light_palette)
        if dark_palette:
            self._dark_palette = copy.deepcopy(dark_palette)
        else:
            self._dark_palette = copy.deepcopy(light_palette)

    def register_qss_path(self, qss_path: str):
        if os.path.exists(qss_path):
            self._qss_paths.append(qss_path)
            self._load_qss_template()
        else:
            theme_logger.warning(f"QSS file not found: {qss_path}")

    def get_color(self, color_key: str) -> QColor:
        palette = self._dark_palette if self.is_dark() else self._light_palette
        value = palette.get(color_key)

        if isinstance(value, QColor):
            return QColor(value)
        if isinstance(value, str):
            return QColor(value)
        return QColor("#000000")

    def set_color(self, color_key: str, color: QColor):

        color_to_store = QColor(color) if isinstance(color, QColor) else QColor(str(color))
        if self.is_dark():
            self._dark_palette[color_key] = color_to_store
        else:
            self._light_palette[color_key] = color_to_store
        self._apply_theme()
        self.theme_changed.emit()

    def get_current_theme(self) -> str:
        return self._current_theme

    def is_dark(self) -> bool:
        return self._current_theme == "dark"

    def set_theme(self, theme_name: str, app=None):
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
        templates = []
        for qss_path in self._qss_paths:
            if os.path.exists(qss_path):
                try:
                    with open(qss_path, "r", encoding="utf-8") as f:
                        templates.append(f.read())
                    theme_logger.info(f"Loaded QSS part from: {qss_path}")
                except Exception as e:
                    theme_logger.error(f"Error loading QSS {qss_path}: {e}")

        self._qss_template = "\n/* --- NEW FILE --- */\n".join(templates)
        if templates:
            theme_logger.info(f"Loaded {len(templates)} QSS file(s)")
        else:
            theme_logger.warning("Could not find any registered QSS file")

    def apply_theme_to_app(self, app):
        palette_data = self._dark_palette if self.is_dark() else self._light_palette

        if not palette_data:
            theme_logger.warning("No palettes registered, skipping theme application")
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
        app = QApplication.instance()
        if app is None:
            return

        self.apply_theme_to_app(app)

    def apply_theme_to_dialog(self, dialog):

        palette_data = self._dark_palette if self.is_dark() else self._light_palette

        if not palette_data:
            theme_logger.warning("No palettes registered, skipping dialog theme application")
            return

        q_palette = dialog.palette()
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

        dialog.setPalette(q_palette)

        dialog.style().unpolish(dialog)
        dialog.style().polish(dialog)
        dialog.updateGeometry()
        dialog.update()

