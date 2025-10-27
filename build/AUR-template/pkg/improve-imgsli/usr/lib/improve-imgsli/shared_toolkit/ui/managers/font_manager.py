import os
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

class FontManager(QObject):
    """Manager for managing application fonts."""

    _instance = None
    font_changed = pyqtSignal()

    @classmethod
    def get_instance(cls):
        """Get the single instance of FontManager."""
        if cls._instance is None:
            cls._instance = FontManager()
        return cls._instance

    def __init__(self):
        if FontManager._instance is not None:
            raise RuntimeError("FontManager is a singleton, use get_instance()")
        super().__init__()

        self._current_mode: str = "builtin"
        self._current_family: str = ""

        current_file = Path(__file__).resolve()

        project_root = current_file.parent.parent.parent.parent.parent
        self._built_in_font_path = project_root / "src" / "shared_toolkit" / "resources" / "fonts" / "SourceSans3-Regular.ttf"

        self._built_in_family_cache: str | None = None

    def apply_from_state(self, app_state):
        """Apply font settings from app state (for Improve-ImgSLI)."""
        mode = getattr(app_state, "ui_font_mode", "builtin") or "builtin"
        family = getattr(app_state, "ui_font_family", "") or ""
        self.set_font(mode=mode, family=family)

    def apply_from_settings(self, settings_manager):
        """Apply font settings from SettingsManager (for Tkonverter)."""

        try:
            mode = settings_manager.load_ui_font_mode()
            family = settings_manager.load_ui_font_family()

            self.set_font(mode=mode, family=family)
        except Exception as e:

            self.set_font(mode="builtin", family="")

    def _ensure_builtin_loaded(self) -> str | None:
        """Loads built-in font and returns family name."""
        if self._built_in_family_cache:
            return self._built_in_family_cache

        try:
            path = str(self._built_in_font_path)
            if os.path.exists(path):
                font_id = QFontDatabase.addApplicationFont(path)
                families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
                if families:
                    self._built_in_family_cache = families[0]
                    return self._built_in_family_cache
                else:
                    pass
            else:
                pass
        except Exception as e:
            pass
        return None

    def set_font(self, mode: str, family: str = ""):
        """
        Sets application font.

        Args:
            mode: Font mode ('builtin', 'system_default', 'system_custom')
            family: Font family (for system_custom)
        """

        if mode == "system":
            mode = "system_default"
        if mode not in ("builtin", "system_default", "system_custom"):
            mode = "builtin"

        self._current_mode = mode
        self._current_family = family or ""

        app = QApplication.instance()
        if not app:
            return

        try:
            new_font = None
            if mode == "builtin":
                final_family = self._ensure_builtin_loaded()
                if final_family:
                    new_font = QFont(final_family)
                    app.setFont(new_font)
                else:
                    new_font = QFont()
                    app.setFont(new_font)

            elif mode == "system_default":
                try:
                    new_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
                    app.setFont(new_font)
                except Exception as e:
                    new_font = QFont()
                    app.setFont(new_font)

            else:
                final_family = self._current_family or ""
                if final_family:
                    new_font = QFont(final_family)
                    app.setFont(new_font)
                else:
                    new_font = QFont()
                    app.setFont(new_font)

            self._force_widget_update(app)
            self.font_changed.emit()

        except Exception as e:
            fallback_font = QFont()
            app.setFont(fallback_font)

    def _force_widget_update(self, app):
        """Force update all widgets to apply new font."""
        try:
            widgets = app.allWidgets()
            new_app_font = app.font()

            for widget in widgets:
                if widget:
                    try:
                        widget.setFont(new_app_font)
                        widget.style().unpolish(widget)
                        widget.style().polish(widget)
                        widget.update()
                        widget.updateGeometry()
                    except Exception as widget_error:
                        pass
        except Exception as e:
            pass

    def get_current_mode(self) -> str:
        """Get current font mode."""
        return self._current_mode

    def get_current_family(self) -> str:
        """Get current font family."""
        return self._current_family

    def get_builtin_family(self) -> str | None:
        """Get built-in font name."""
        return self._ensure_builtin_loaded()

    def is_builtin_available(self) -> bool:
        """Check if built-in font is available."""
        return self._ensure_builtin_loaded() is not None
