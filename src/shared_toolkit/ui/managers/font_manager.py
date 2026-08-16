import logging
import os
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

_logger = logging.getLogger("ImproveImgSLI")


def _caller_str(depth: int = 6) -> str:
    """Short `file:line:func` chain -- who actually called `set_font()`.
    Local copy of `ui.widgets.glass_hud.hud.caller_str` (not imported: this
    module lives in `shared_toolkit`, app-agnostic, shouldn't depend on
    app-specific `ui.widgets` code)."""
    frames = traceback.extract_stack()[:-2]
    frames = [f for f in frames if "font_manager.py" not in f.filename][-depth:]
    return " <- ".join(f"{f.filename.split('/')[-1]}:{f.lineno}:{f.name}" for f in frames)


class FontManager(QObject):

    _instance = None
    font_changed = Signal()

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

        project_root = current_file.parent.parent.parent.parent
        self._built_in_font_path = (
            project_root
            / "shared_toolkit"
            / "resources"
            / "fonts"
            / "SourceSans3-Regular.ttf"
        )

        self._built_in_family_cache: str | None = None

    def apply_from_state(self, store):

        if hasattr(store, "settings"):

            mode = getattr(store.settings, "ui_font_mode", "builtin") or "builtin"
            family = getattr(store.settings, "ui_font_family", "") or ""
        else:

            mode = getattr(store, "ui_font_mode", "builtin") or "builtin"
            family = getattr(store, "ui_font_family", "") or ""
        self.set_font(mode=mode, family=family)

    def apply_from_settings(self, settings_manager):

        try:
            mode = settings_manager.load_ui_font_mode()
            family = settings_manager.load_ui_font_family()

            self.set_font(mode=mode, family=family)
        except Exception:

            self.set_font(mode="builtin", family="")

    def _ensure_builtin_loaded(self) -> str | None:
        if self._built_in_family_cache:
            return self._built_in_family_cache

        try:
            path = str(self._built_in_font_path)
            if os.path.exists(path):
                font_id = QFontDatabase.addApplicationFont(path)
                families = (
                    QFontDatabase.applicationFontFamilies(font_id)
                    if font_id != -1
                    else []
                )
                if families:
                    self._built_in_family_cache = families[0]
                    return self._built_in_family_cache
        except Exception:
            pass
        return None

    def set_font(self, mode: str, family: str = ""):
        _logger.debug(
            "[flyout-debug] FontManager.set_font(mode=%r, family=%r) "
            "previous_mode=%r previous_family=%r caller=%s",
            mode,
            family,
            self._current_mode,
            self._current_family,
            _caller_str(),
        )

        if mode == "system":
            mode = "system_default"
        if mode not in ("builtin", "system_default", "system_custom"):
            mode = "builtin"

        self._current_mode = mode
        self._current_family = family or ""

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return

        try:
            new_font = None
            if mode == "builtin":
                final_family = self._ensure_builtin_loaded()
                if final_family:
                    new_font = QFont(final_family)
                else:
                    new_font = QFont()

            elif mode == "system_default":
                try:
                    new_font = QFontDatabase.systemFont(
                        QFontDatabase.SystemFont.GeneralFont
                    )
                except Exception:
                    new_font = QFont()

            else:
                final_family = self._current_family or ""
                if final_family:
                    new_font = QFont(final_family)
                else:
                    new_font = QFont()

            if new_font.pointSize() <= 8:
                new_font.setPointSize(11)

            _logger.debug(
                "[flyout-debug] FontManager.set_font: app.setFont() family=%r "
                "pointSizeF=%.2f (was family=%r pointSizeF=%.2f)",
                new_font.family(),
                new_font.pointSizeF(),
                app.font().family(),
                app.font().pointSizeF(),
            )
            app.setFont(new_font)

            try:
                from sli_ui_toolkit.managers import UiFont

                ui = UiFont.get_instance()
                # Pin the resolved family so toolkit widgets don't race
                # ApplicationFontChange / bake a pre-apply system face.
                ui.set_family(new_font.family() or None)
                ui.sync_from_application()
            except Exception:
                pass

            self._force_widget_update(app)
            self.font_changed.emit()

        except Exception:
            fallback_font = QFont()
            fallback_font.setPointSize(11)
            app.setFont(fallback_font)
            try:
                from sli_ui_toolkit.managers import UiFont

                ui = UiFont.get_instance()
                ui.set_family(fallback_font.family() or None)
                ui.sync_from_application()
            except Exception:
                pass

    def _force_widget_update(self, app):
        try:
            for widget in app.allWidgets():
                if widget and not widget.objectName().startswith("qt_"):
                    try:
                        widget.style().unpolish(widget)
                        widget.style().polish(widget)
                        widget.updateGeometry()
                        widget.update()
                    except Exception:
                        pass
        except Exception:
            pass

    def get_current_mode(self) -> str:
        return self._current_mode

    def get_current_family(self) -> str:
        return self._current_family

    def get_builtin_family(self) -> str | None:
        return self._ensure_builtin_loaded()

    def is_builtin_available(self) -> bool:
        return self._ensure_builtin_loaded() is not None

    def get_current_font_path(self) -> str | None:
        if self._current_mode == "builtin":
            path = str(self._built_in_font_path)
            if os.path.exists(path):
                return path
        return None

    def get_font_path_for_image_text(self, store) -> str | None:
        try:
            if hasattr(store, "settings"):
                mode = getattr(store.settings, "ui_font_mode", "builtin") or "builtin"
            else:
                mode = getattr(store, "ui_font_mode", "builtin") or "builtin"

            if mode == "system":
                mode = "system_default"

            if mode == "builtin":
                path = str(self._built_in_font_path)
                if os.path.exists(path):
                    return path

            return None
        except Exception:
            return None