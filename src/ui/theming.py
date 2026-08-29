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


def tint_scroll_surface(scroll_area: QWidget, color_key: str = "dialog.background") -> None:
    """Paint a stock ``QScrollArea`` surface from a theme token.

    Stock scroll areas and their viewports auto-fill the QPalette Window
    role, which hosts keep darker than the dialog surface token (dark
    ``Window`` ``#1e1e1e`` vs ``dialog.background`` ``#2b2b2b``) — the
    empty area behind transparent custom content (hub pages, document
    views) then renders near-black against the gray panels. A per-widget
    palette is NOT enough: ``QStyle::polish`` at ``show()`` (and on any
    host stylesheet re-apply) resets widget palettes to the app palette. A
    widget-level ``background-color`` survives polish and cascades to the
    viewport and the content widget — same mechanism as the toolkit's
    ``ScrollableDialogPage._apply_dialog_surface``. Re-call on every
    ``theme_changed`` so token overrides via ``set_color`` take effect.
    """
    from sli_ui_toolkit.managers import ThemeManager

    try:
        color = try_resolve_theme_color(ThemeManager.get_instance(), color_key)
    except Exception:
        color = None
    if color is None or not color.isValid():
        color = QColor(scroll_area.palette().window().color())
    scroll_area.setStyleSheet(f"background-color: {color.name()};")


def reapply_application_theme(app: QApplication) -> None:
    """Re-run the full theme apply (colors + QSS px scaling) through UI infra.

    Used after runtime settings that change rendered chrome — e.g. the UI
    scale factor, whose Npx QSS scaling pass runs inside
    ``ThemeManager.apply_theme_to_app``.
    """
    from sli_ui_toolkit.managers import ThemeManager

    ThemeManager.get_instance().apply_theme_to_app(app)