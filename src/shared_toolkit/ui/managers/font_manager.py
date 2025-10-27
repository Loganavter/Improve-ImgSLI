import logging
import os
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger("ImproveImgSLI")

def _safe_log(level, message, show_exc=False):
    if logger.hasHandlers():
        if level == 'debug':
            logger.debug(message)
        elif level == 'info':
            logger.info(message)
        elif level == 'warning':
            if show_exc:
                logger.warning(message, exc_info=True)
            else:
                logger.warning(message)
        elif level == 'error':
            if show_exc:
                logger.error(message, exc_info=True)
            else:
                logger.error(message)
    else:

        print(f"[FontManager] {message}")

class FontManager(QObject):

    _instance = None
    font_changed = pyqtSignal()

    @classmethod
    def get_instance(cls):
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

        path_parts = current_file.parts

        if 'src' in path_parts:

            idx = path_parts.index('src')
            project_root = Path(*path_parts[:idx])
            self._built_in_font_path = project_root / "src" / "shared_toolkit" / "resources" / "fonts" / "SourceSans3-Regular.ttf"
        else:

            self._built_in_font_path = current_file.parent.parent.parent / "resources" / "fonts" / "SourceSans3-Regular.ttf"

        self._built_in_family_cache: str | None = None

    def apply_from_state(self, app_state):
        mode = getattr(app_state, "ui_font_mode", "builtin") or "builtin"
        family = getattr(app_state, "ui_font_family", "") or ""
        self.set_font(mode=mode, family=family)

    def apply_from_settings(self, settings_manager):

        try:
            mode = settings_manager.load_ui_font_mode()
            family = settings_manager.load_ui_font_family()

            self.set_font(mode=mode, family=family)
        except Exception as e:
            _safe_log('error', f"Exception in apply_from_settings: {e}", show_exc=True)
            self.set_font(mode="builtin", family="")

    def _ensure_builtin_loaded(self) -> str | None:
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
                    _safe_log('warning', f"Failed to load built-in font: no families found (font_id={font_id})")
            else:
                _safe_log('error', f"Built-in font file not found at path: {path}")
        except Exception as e:
            _safe_log('error', f"Exception while loading built-in font: {e}")
        return None

    def set_font(self, mode: str, family: str = ""):

        if mode == "system":
            mode = "system_default"
        if mode not in ("builtin", "system_default", "system_custom"):
            mode = "builtin"

        self._current_mode = mode
        self._current_family = family or ""

        app = QApplication.instance()
        if not app:
            _safe_log('warning', "QApplication.instance() is None, cannot set font")
            return

        try:
            new_font = None
            if mode == "builtin":
                final_family = self._ensure_builtin_loaded()
                if final_family:
                    new_font = QFont(final_family)
                    app.setFont(new_font)
                else:
                    _safe_log('warning', "Builtin font not available, using default")
                    new_font = QFont()
                    app.setFont(new_font)

            elif mode == "system_default":
                try:
                    new_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
                    app.setFont(new_font)
                except Exception as e:
                    _safe_log('warning', f"Failed to load system default font: {e}")
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
            _safe_log('error', f"Exception while setting font (mode={mode}): {e}", show_exc=True)
            fallback_font = QFont()
            app.setFont(fallback_font)

    def _force_widget_update(self, app):
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
                    except Exception:
                        pass
        except Exception as e:
            _safe_log('warning', f"Exception while forcing widget update: {e}", show_exc=True)

    def get_current_mode(self) -> str:
        return self._current_mode

    def get_current_family(self) -> str:
        return self._current_family

    def get_builtin_family(self) -> str | None:
        return self._ensure_builtin_loaded()

    def is_builtin_available(self) -> bool:
        return self._ensure_builtin_loaded() is not None
