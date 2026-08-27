from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QWidget


def polish_themed_dialog(theme_manager, dialog: QWidget) -> None:
    """Apply app theming to standalone Qt dialogs through one UI-infra hook."""
    theme_manager.apply_theme_to_dialog(dialog)


def install_application_theme(app_context, app) -> None:
    """Install app theming through one UI-infra hook."""
    app_context.apply_theme_to_app(app)


def resolve_theme_color(theme_manager, color_key: str) -> QColor:
    """Resolve a theme token for custom-painted or programmatic-color widgets."""
    return theme_manager.get_color(color_key)


def try_resolve_theme_color(theme_manager, color_key: str) -> QColor | None:
    """Resolve a theme token, returning ``None`` when the key is absent.

    Thin infra wrapper over ``ThemeManager.try_get_color`` so feature code can
    degrade to a fallback color without touching manager internals directly.
    """
    return theme_manager.try_get_color(color_key)


def refresh_application_styles(app: QApplication) -> None:
    """Re-polish application QSS after runtime style-affecting settings change."""
    app.setStyleSheet(app.styleSheet())


def reapply_application_theme(app: QApplication) -> None:
    """Re-run the full theme apply (colors + QSS px scaling) through UI infra.

    Used after runtime settings that change rendered chrome — e.g. the UI
    scale factor, whose Npx QSS scaling pass runs inside
    ``ThemeManager.apply_theme_to_app``.
    """
    from sli_ui_toolkit.managers import ThemeManager

    ThemeManager.get_instance().apply_theme_to_app(app)