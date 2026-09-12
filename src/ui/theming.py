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


def refresh_application_styles(app: QApplication) -> None:
    """Re-polish application QSS after runtime style-affecting settings change."""
    app.setStyleSheet(app.styleSheet())
