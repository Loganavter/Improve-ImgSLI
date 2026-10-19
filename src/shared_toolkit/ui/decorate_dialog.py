"""App-side wrapper around toolkit `decorate_dialog`.

Resolves AppIcon-named window-control icons before delegating to
``sli_ui_toolkit.decorate_dialog``.

Also installs an application-wide event filter that auto-decorates any
``QDialog`` / ``QMessageBox`` that's about to be shown for the first time —
otherwise error/warning popups would slip through with the OS native frame.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from sli_ui_toolkit import CustomTitleBar, decorate_dialog as _toolkit_decorate_dialog
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import DEFER_CLICK_AWAIT_RIPPLE
from ui.theming import polish_themed_dialog, resolve_theme_color

CUSTOM_DECORATION_RESIZE_MARGIN = 8

#: Standard CSD window-control roles (the titlebarRole widget property). The
#: toolkit creates these mouse-only (``NoFocus``); a dialog whose title bar is
#: keyboard-navigable has to make them focus stops itself, otherwise the bar
#: section has nothing to land on.
_WINDOW_CONTROL_ROLES = frozenset({"min", "max", "close"})

_TITLE_BAR_NAV_SECTION_ATTR = "_title_bar_nav_section"
_DIALOG_TITLE_BAR_SECTION_CLS = None


def _dialog_title_bar_section_cls():
    """Lazily build the dialog-title-bar section class.

    Subclasses the settings/host ``TitleBarNavigationSection`` (same
    Left/Right delegation to ``CustomTitleBar``, same Up consumption) and adds
    only the Down fallback a *dialog* needs: when the dialog's own row section
    is registered after the bar (the modal video editor registers the bar
    above its ceiling — see ``register_dialog_title_bar_navigation``) registry
    adjacency points the wrong way, so Down enters the dialog section by
    identity instead of relying on the manager's neighbour hand-off.
    """
    global _DIALOG_TITLE_BAR_SECTION_CLS
    if _DIALOG_TITLE_BAR_SECTION_CLS is not None:
        return _DIALOG_TITLE_BAR_SECTION_CLS

    from ui.main_window.title_bar_navigation import TitleBarNavigationSection

    class _DialogTitleBarNavigationSection(TitleBarNavigationSection):
        def __init__(self, title_bar: QWidget, dialog: QDialog) -> None:
            super().__init__(title_bar)
            self._dialog = dialog

        def navigate(self, key: int, widget: QWidget) -> bool:
            if key == Qt.Key.Key_Down:
                from sli_ui_toolkit.managers import NavigationManager

                if NavigationManager.get_instance().focus_section_for_owner(
                    self._dialog
                ):
                    return True
            return super().navigate(key, widget)

    _DIALOG_TITLE_BAR_SECTION_CLS = _DialogTitleBarNavigationSection
    return _DIALOG_TITLE_BAR_SECTION_CLS


def _make_window_controls_focusable(title_bar: QWidget) -> None:
    """Turn the bar's mouse-only window controls into keyboard focus stops."""
    for control in title_bar.findChildren(QWidget):
        try:
            if control.property("titlebarRole") in _WINDOW_CONTROL_ROLES:
                control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        except (RuntimeError, TypeError):
            continue


def register_dialog_title_bar_navigation(dialog: QDialog):
    """Own a CSD-decorated dialog's title bar (idempotent).

    Call before the dialog's own row section is registered so the bar is the
    topmost section and Down/Up hand off in visual order — or from a
    ``showEvent`` (before or after the rows) for dialogs the app-wide
    decorator builds at Polish time, where the earlier callback only adds the
    Down fallback. No-op until ``_csd_title_bar`` exists; returns the
    registered section, or ``None`` when the dialog has no CSD bar. The
    signature follows the settings shell helper; the only addition is the
    Down fallback for a dialog whose row section is registered after the bar
    (see ``_dialog_title_bar_section_cls``).
    """
    title_bar = getattr(dialog, "_csd_title_bar", None)
    if title_bar is None:
        return None

    section = getattr(dialog, _TITLE_BAR_NAV_SECTION_ATTR, None)
    if section is None:
        _make_window_controls_focusable(title_bar)
        section = _dialog_title_bar_section_cls()(title_bar, dialog)
        dialog._title_bar_nav_section = section  # type: ignore[attr-defined]  # dynamic attr
    try:
        from sli_ui_toolkit.managers import NavigationManager

        NavigationManager.get_instance().register(title_bar, section)
    except Exception:
        return section
    return section


def unregister_dialog_title_bar_navigation(dialog: QDialog) -> None:
    """Drop the dialog title-bar section (idempotent)."""
    section = getattr(dialog, _TITLE_BAR_NAV_SECTION_ATTR, None)
    if section is None:
        return
    title_bar = getattr(dialog, "_csd_title_bar", None)
    if title_bar is not None:
        try:
            from sli_ui_toolkit.managers import NavigationManager

            NavigationManager.get_instance().unregister(title_bar)
        except Exception:
            pass
    dialog._title_bar_nav_section = None  # type: ignore[attr-defined]  # dynamic attr


def resolve_csd_band(window) -> int:
    """Effective CSD outer-band inset for ``window``.

    The frameless surface carries a transparent outer band (resize-grab
    margin) beyond the visible body. Maximized/fullscreen windows cannot be
    edge-resized, so the band (and everything inset by it — the painted
    body, the root-layout content) must collapse to 0 there; otherwise an
    invisible strip remains around the window that window-capture tools
    include (painted with the window background once the body fills the
    surface).
    """
    if window.isMaximized() or window.isFullScreen():
        return 0
    try:
        return int(window.property("_csd_outer_band") or 0)
    except Exception:
        return 0


_MSGBOX_TITLE_BY_ICON = {
    QMessageBox.Icon.Critical: "Error",
    QMessageBox.Icon.Warning: "Warning",
    QMessageBox.Icon.Information: "Information",
    QMessageBox.Icon.Question: "Confirm",
}


def _resolve_dialog_title(dialog: QDialog) -> str:
    title = dialog.windowTitle() or ""
    if title:
        return title
    if isinstance(dialog, QMessageBox):
        return _MSGBOX_TITLE_BY_ICON.get(dialog.icon(), "Message")
    return ""


def decorate_dialog(
    dialog: QDialog,
    *,
    title: str = "",
    show_minimize: bool = False,
    show_maximize: bool = False,
    show_close: bool = True,
    resizable: bool = True,
    # Closing a dialog can do real work (session save, plugin teardown) —
    # let the close button's press ripple finish first by default. Pass
    # None to opt a specific dialog out and keep the sync (instant) click.
    defer_close_click: object = DEFER_CLICK_AWAIT_RIPPLE,
) -> CustomTitleBar | None:
    existing = getattr(dialog, "_csd_title_bar", None)
    if existing is not None:
        return existing if isinstance(existing, CustomTitleBar) else None
    # polish_themed_dialog can re-enter via the app Polish interceptor and
    # stack a second CustomTitleBar.HEIGHT onto the layout top margin.
    if bool(getattr(dialog, "_csd_decorating", False)):
        return None

    from ui.icon_manager import AppIcon

    dialog._csd_decorating = True  # type: ignore[attr-defined]  # dynamic attr
    try:
        theme_manager = ThemeManager.get_instance()
        polish_themed_dialog(theme_manager, dialog)

        title_bar = _toolkit_decorate_dialog(
            dialog,
            title=title,
            minimize_icon=AppIcon.MINIMIZE,
            maximize_icon=AppIcon.MAXIMIZE,
            restore_icon=AppIcon.RESTORE,
            close_icon=AppIcon.WINDOW_CLOSE,
            show_minimize=show_minimize,
            show_maximize=show_maximize,
            show_close=show_close,
            resizable=resizable,
            resize_margin=CUSTOM_DECORATION_RESIZE_MARGIN,
            defer_close_click=defer_close_click,
        )
        return title_bar
    finally:
        dialog._csd_decorating = False  # type: ignore[attr-defined]  # dynamic attr


def install_dialog_help_menu(
    dialog: QDialog,
    *,
    page: str | None = None,
    anchor: str | None = None,
    title_bar: CustomTitleBar | None = None,
) -> object | None:
    """Install the main-window Help menu (label + dropdown) on a dialog title bar.

    Same entries as the host Help menu: Show Help and Find Action. Leading
    zone, left of the title — mirrors ``MainWindowMenuController`` Help.
    Idempotent; no-op when decorations are off / title bar missing.
    """
    existing = getattr(dialog, "_csd_help_menu_strip", None)
    if existing is not None:
        return existing

    bar = title_bar if title_bar is not None else getattr(dialog, "_csd_title_bar", None)
    if bar is None:
        return None
    set_leading = getattr(bar, "set_leading", None)
    if not callable(set_leading):
        return None

    from resources.translations import get_current_language, tr
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
    from ui.actions.palette.dialog import open_help_page
    from ui.main_window.csd_menu_strip import CsdMenuSpec, CsdMenuStrip

    lang = get_current_language() or "en"

    def _tr(key: str, fallback: str) -> str:
        text = tr(key, lang)
        return fallback if text == key else text

    def _on_triggered(action_id: str, _data: object) -> None:
        if action_id == "help.show":
            open_help_page(page or "workspace.export", anchor)
            return
        if action_id == "help.find_action":
            from ui.actions.palette import show_command_palette

            owner = getattr(dialog, "_find_action_owner_tab", None)
            show_command_palette(parent=dialog, active_tab=owner)

    try:
        from ui.icon_manager import themed_icon as _themed_icon
    except Exception:
        _themed_icon = None  # type: ignore[assignment]

    def _icon(name: str):
        try:
            return _themed_icon(name) if _themed_icon is not None else None
        except Exception:
            return None

    strip = CsdMenuStrip(
        [
            CsdMenuSpec(
                label=_tr("menu.help", "Help"),
                entries=[
                    ContextMenuAction(
                        "help.show",
                        _tr("menu.show_help", "Show Help"),
                        icon=_icon("help.svg"),
                    ),
                    ContextMenuSeparator(),
                    ContextMenuAction(
                        "help.find_action",
                        _tr("menu.find_action", "Find Action"),
                        icon=_icon("magnifier.svg"),
                        shortcut="Ctrl+Shift+P",
                    ),
                ],
                on_triggered=_on_triggered,
            )
        ],
        parent=bar,
    )
    set_leading(strip)
    dialog._csd_help_menu_strip = strip  # type: ignore[attr-defined]  # dynamic attr
    return strip


# Back-compat alias used by early call sites / tests.
install_dialog_help_button = install_dialog_help_menu


def configure_custom_decoration_resize_margin() -> None:
    """Widen toolkit frameless resize hit target for custom-decorated dialogs."""
    from sli_ui_toolkit.ui.windows import frameless

    frameless.RESIZE_MARGIN = CUSTOM_DECORATION_RESIZE_MARGIN


class _DialogDecorationInterceptor(QObject):
    """Catch every top-level QDialog at Polish-time and decorate it.

    Polish fires once during widget setup, before the window is mapped onto
    the screen — calling :func:`decorate_dialog` here means the frameless flag
    is applied while the QWindow is still hidden, so there is no visible
    flicker. Dialogs that already carry ``_csd_title_bar`` (i.e. explicitly
    decorated by their authors) are skipped. Set ``_csd_opt_out = True`` on a
    dialog instance to bypass this filter entirely.
    """

    def eventFilter(self, watched, event):
        try:
            if event.type() != QEvent.Type.Polish:
                return False
            if not isinstance(watched, QDialog):
                return False
            if not watched.isWindow():
                return False
            if getattr(watched, "_csd_title_bar", None) is not None:
                return False
            if bool(getattr(watched, "_csd_decorating", False)):
                return False
            if bool(getattr(watched, "_csd_opt_out", False)):
                return False
            decorate_dialog(watched, title=_resolve_dialog_title(watched))
        except (RuntimeError, AttributeError, TypeError):
            return False
        except Exception:
            pass
        return False


def install_application_dialog_decorations(app: QApplication | None) -> None:
    """Install the app-wide auto-decoration filter (idempotent)."""
    if app is None or getattr(app, "_csd_filter_installed", False):
        return
    interceptor = _DialogDecorationInterceptor(app)
    app.installEventFilter(interceptor)
    app._csd_filter_installed = True  # type: ignore[attr-defined]  # dynamic attr
    app._csd_filter = interceptor  # type: ignore[attr-defined]  # dynamic attr