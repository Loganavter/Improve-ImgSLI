"""Host-level title bar menus (File, Help) and platform action runners."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from resources.translations import tr, translation_events
from sli_ui_toolkit import TitleBarPresets, WindowControlsConfig
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuSeparator,
    DEFER_CLICK_AWAIT_RIPPLE,
)
from ui.main_window.csd_menu_strip import CsdMenuSpec, CsdMenuStrip, csd_debug
from ui.main_window.project_io import MainWindowProjectIo
from ui.main_window.use_cases import platform_actions, settings_navigation

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

logger = logging.getLogger("ImproveImgSLI")


class MainWindowMenuController:
    """Host-level title bar menus (File, Help).

    Project open/save lives in :class:`MainWindowProjectIo` (``self.project_io``).
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._menu_strip: CsdMenuStrip | None = None
        self._find_action_shortcut = None
        self._contextual_palette_shortcut = None
        self.project_io = MainWindowProjectIo(window, tr=self._tr)
        translation_events().language_changed.connect(self._on_language_changed)

    def _language(self) -> str:
        try:
            return self._window.store.settings.current_language
        except Exception:
            return "en"

    def _tr(self, key: str, fallback: str) -> str:
        translated = tr(key, self._language())
        return fallback if translated == key else translated

    def _presenter(self):
        return getattr(self._window, "presenter", None)

    def _ui_manager(self):
        presenter = self._presenter()
        return getattr(presenter, "ui_manager", None) if presenter is not None else None

    def _workspace(self):
        presenter = self._presenter()
        controller = getattr(presenter, "main_controller", None) if presenter else None
        return getattr(controller, "workspace", None) if controller is not None else None

    def build_title_bar(self):
        from ui.icon_manager import AppIcon

        window = self._window
        strip = self.build_menus()
        self._menu_strip = strip
        shell_parent = window if isinstance(window, QWidget) else None
        bar = TitleBarPresets.app_shell(
            title=window.windowTitle() or "Improve ImgSLI",
            parent=shell_parent,
            controls=WindowControlsConfig(
                minimize_icon=AppIcon.MINIMIZE,
                maximize_icon=AppIcon.MAXIMIZE,
                restore_icon=AppIcon.RESTORE,
                close_icon=AppIcon.WINDOW_CLOSE,
                # Closing the main window tears down the whole app (session
                # save, plugin shutdown) — let the press ripple finish first.
                defer_close_click=DEFER_CLICK_AWAIT_RIPPLE,
            ),
        )
        # The title bar is a generic shell; the app injects its own CSD menu
        # strip (trigger buttons + app-decided popup/in-window surface).
        bar.set_leading(strip)
        bar.attach_window(window)
        self._install_undo_redo_buttons(bar)
        self._wire_undo_redo_refresh()
        self._register_platform_actions()
        self._resync_action_shortcuts()
        return bar

    def _install_undo_redo_buttons(self, bar) -> None:
        """CSD undo/redo controls after the menu strip (leading zone).

        Styled like the File/Help menu triggers (ghost, radius 6, trigger
        height, titlebar.text foreground); disabled buttons render at reduced
        opacity via a QGraphicsOpacityEffect.

        May be called more than once: ``set_leading`` (menu strip rebuild on
        language change) clears the whole leading zone, so the buttons are
        reinstalled after it.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from sli_ui_toolkit.ui.widgets.buttons import Button
        from sli_ui_toolkit.ui.windows.custom_title_bar import (
            CustomTitleBar,
            resolve_titlebar_color,
        )

        from ui.icon_manager import AppIcon

        trigger_h = max(20, CustomTitleBar.HEIGHT - 2 * 4)

        def _mk(icon, role: str, tooltip_key: str, tooltip_fallback: str, run, *, pad_left: int = 0):
            btn = Button(
                icon,
                variant="ghost",
                size=(40, trigger_h),
                icon_size=16,
                corner_radius=6,
                content_padding=(pad_left, 0, 0, 0),
                parent=bar,
            )
            btn.setObjectName("CustomTitleBarButton")
            btn.setProperty("titlebarRole", role)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setForegroundColor(
                resolve_titlebar_color("titlebar.text", fallback="WindowText")
            )
            btn.setToolTip(self._tr(tooltip_key, tooltip_fallback))
            btn.clicked.connect(run)
            btn.setEnabled(False)
            effect = QGraphicsOpacityEffect(btn)
            effect.setOpacity(0.4)
            btn.setGraphicsEffect(effect)
            return btn, effect

        self._undo_button, self._undo_effect = _mk(
            AppIcon.UNDO, "undo", "action.platform.undo", "Undo", self._undo, pad_left=10
        )
        self._redo_button, self._redo_effect = _mk(
            AppIcon.REDO, "redo", "action.platform.redo", "Redo", self._redo
        )
        bar.add_buttons([self._undo_button, self._redo_button], zone="leading")

    def _wire_undo_redo_refresh(self) -> None:
        """Connect store changes to the CSD undo/redo enabled state.

        Called once (``build_title_bar``): re-installing the buttons after a
        menu-strip rebuild must not re-subscribe the store handler.
        """
        from PySide6.QtCore import QTimer

        store = getattr(self._window, "store", None)
        if store is not None and hasattr(store, "on_change"):
            # emit_state_change fires inside the dispatcher lock (undo/redo
            # read the stacks under the same lock), so defer the refresh.
            store.on_change(lambda _scope, s=self: QTimer.singleShot(0, s._refresh_undo_redo_enabled))
        self._refresh_undo_redo_enabled()

    def _refresh_undo_redo_enabled(self, _scope: str = "") -> None:
        if not hasattr(self, "_undo_button"):
            return
        try:
            from shiboken6 import isValid

            # ``set_leading`` clears the whole leading zone on menu rebuilds;
            # a stale ref (or a pending refresh tick after a rebuild) must
            # not hit a deleted C++ button.
            if not isValid(self._undo_button) or not isValid(self._redo_button):
                return
        except ImportError:
            pass
        try:
            dispatcher = getattr(self._window.store, "get_dispatcher", lambda: None)()
        except Exception:
            dispatcher = None
        can_undo = bool(dispatcher is not None and dispatcher.can_undo())
        can_redo = bool(dispatcher is not None and dispatcher.can_redo())
        self._undo_button.setEnabled(can_undo)
        self._redo_button.setEnabled(can_redo)
        self._undo_effect.setOpacity(1.0 if can_undo else 0.4)
        self._redo_effect.setOpacity(1.0 if can_redo else 0.4)

    def _app_icon(self):
        from PySide6.QtGui import QIcon

        from utils.resource_loader import resource_path

        return QIcon(resource_path("resources/icons/icon.png"))

    def build_menus(self) -> CsdMenuStrip:
        language = self._language()
        parent = self._window if isinstance(self._window, QWidget) else None
        csd_debug("build_menus language=%r file=%r help=%r", language,
                  tr("menu.file", language), tr("menu.help", language))
        return CsdMenuStrip(
            [
                CsdMenuSpec(
                    label=tr("menu.file", language),
                    icon=self._app_icon(),
                    entries=self._file_context_entries(),
                    on_triggered=self._on_file_action,
                ),
                CsdMenuSpec(
                    label=tr("menu.help", language),
                    entries=self._help_context_entries(),
                    on_triggered=self._on_help_action,
                ),
            ],
            parent=parent,
        )

    def _keyboard_overrides(self) -> dict[str, str]:
        try:
            overrides = getattr(self._window.store.settings, "keyboard_overrides", None)
            if isinstance(overrides, dict):
                return dict(overrides)
        except Exception:
            pass
        try:
            from ui.actions.palette.common import current_keyboard_overrides

            return current_keyboard_overrides()
        except Exception:
            return {}

    def _menu_shortcut(self, action_id: str, default: str | None) -> str | None:
        """Effective chord for a CSD menu row (defaults + Settings overrides)."""
        from ui.actions.keymap import effective_shortcut_for_id

        return effective_shortcut_for_id(
            action_id,
            default=default,
            overrides=self._keyboard_overrides(),
        )

    def _file_context_entries(self) -> list[object]:
        return [
            ContextMenuAction(
                action_id="file.new_session",
                text=self._tr("menu.new_session", "New Session"),
                shortcut=self._menu_shortcut("platform.new_session", "Ctrl+N"),
            ),
            ContextMenuAction(
                action_id="file.open_project",
                text=self._tr("menu.open_project", "Open Project"),
                shortcut=self._menu_shortcut("platform.open_project", "Ctrl+Shift+O"),
            ),
            ContextMenuAction(
                action_id="file.save_project",
                text=self._tr("menu.save_project", "Save Project"),
                shortcut=self._menu_shortcut("platform.save_project", "Shift+S"),
            ),
            ContextMenuAction(
                action_id="file.save_project_as",
                text=self._tr("menu.save_project_as", "Save Project As…"),
                shortcut=self._menu_shortcut(
                    "platform.save_project_as", "Ctrl+Shift+S"
                ),
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                action_id="file.settings",
                text=self._tr("menu.settings", "Settings"),
                shortcut=self._menu_shortcut("platform.settings", "Ctrl+,"),
                # Row click always hides (and destroys) this menu
                # synchronously regardless of what the action does next --
                # without this the row's own click ripple never gets to
                # play at all, same as help.find_action below.
                defer_trigger=True,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                action_id="file.quit",
                text=self._tr("menu.quit", "Quit"),
                shortcut=self._menu_shortcut("platform.quit", "Ctrl+Q"),
            ),
        ]

    def _help_context_entries(self) -> list[object]:
        return [
            ContextMenuAction(
                action_id="help.show",
                text=self._tr("menu.show_help", "Help"),
                shortcut=self._menu_shortcut("platform.help", "Ctrl+F1"),
                defer_trigger=True,
            ),
            ContextMenuAction(
                action_id="help.find_action",
                text=self._tr("menu.find_action", "Find Action…"),
                shortcut=self._menu_shortcut("platform.find_action", "Ctrl+Shift+P"),
                # Opens the modal Find Action palette (dialog.exec()) --
                # without this the row (and its click ripple) is destroyed
                # by the menu closing before the ripple gets to play at all.
                defer_trigger=True,
            ),
        ]

    def _on_language_changed(self, _lang: str) -> None:
        # Rebuild the strip instead of mutating labels in place: after other
        # tests tear down windows, the old Button children may already be
        # deleted (PySide RuntimeError on setText / updateGeometry).
        title_bar = getattr(self._window, "_custom_title_bar", None)
        if title_bar is None:
            return
        try:
            from shiboken6 import isValid

            if not isValid(title_bar):
                self._menu_strip = None
                return
        except ImportError:
            pass

        language = self._language()
        file_label = tr("menu.file", language)
        help_label = tr("menu.help", language)
        existing = self._menu_strip
        # setupUi emits language_changed after the shell already built menus
        # for the same language. Rebuilding then leaves two strips until
        # deleteLater runs — both paint on first show.
        if existing is not None:
            try:
                from shiboken6 import isValid

                if isValid(existing):
                    menus = getattr(existing, "_menus", None) or []
                    if (
                        len(menus) >= 2
                        and menus[0].label == file_label
                        and menus[1].label == help_label
                    ):
                        self._register_platform_actions()
                        self._resync_action_shortcuts()
                        return
            except Exception:
                pass

        try:
            new_strip = self.build_menus()
            self._menu_strip = new_strip
            title_bar.set_leading(new_strip)
            # ``set_leading`` clears the whole leading zone — including the
            # CSD undo/redo buttons added after the strip. Reinstall them so
            # the next store change cannot hit deleted C++ buttons.
            self._install_undo_redo_buttons(title_bar)
            self._register_platform_actions()
        except RuntimeError:
            self._menu_strip = None
            return

    def _on_help_action(self, action_id: str, _data: object) -> None:
        if action_id == "help.show":
            self._show_help()
        elif action_id == "help.find_action":
            self._show_find_action()

    def _on_file_action(self, action_id: str, _data: object) -> None:
        handlers = {
            "file.new_session": self._new_session,
            "file.open_project": self._open_project,
            "file.save_project": self._save_project,
            "file.save_project_as": self._save_project_as,
            "file.settings": self._show_settings,
            "file.quit": self._quit,
        }
        handler = handlers.get(action_id)
        if handler is not None:
            handler()

    def _new_session(self) -> None:
        from tabs.registry import TabRegistry

        # bootstrap_default_tab() is reserved exclusively for session_picker
        # (the app's initial workspace session), so File → New Session opens
        # the session picker — same target as the workspace `+` button.
        tab = TabRegistry().bootstrap_default_tab()
        if tab is None:
            return
        self._create_workspace_session(tab.session_type)

    def _create_workspace_session(self, session_type: str) -> None:
        workspace = self._workspace()
        if workspace is None:
            return
        try:
            workspace.create_workspace_session(session_type, activate=True)
        except Exception:
            logger.exception(
                "Failed to create workspace session from host menu (%s)",
                session_type,
            )

    def _open_project(self) -> None:
        self.project_io.open_project()

    def open_project_at_path(self, path: str) -> None:
        """Load a project file (File → Open and Session Picker recent)."""
        self.project_io.open_project_at_path(path)

    def _save_project(self) -> None:
        self.project_io.save_project()

    def _save_project_as(self) -> None:
        self.project_io.save_project_as()

    def _wire_session_picker_recent(self) -> None:
        """Attach open-project handler to the Session Picker recent panel."""
        self.project_io.wire_session_picker_recent()

    def _show_settings(self) -> None:
        settings_navigation.show_settings(self)

    def _show_settings_section(self, section_id: str) -> None:
        settings_navigation.show_settings_section(self, section_id)

    def _resolve_settings_sidebar(self, section_id: str):
        return settings_navigation.resolve_settings_sidebar(self, section_id)

    def _resolve_settings_group(self, section_id: str, group_key: str):
        return settings_navigation.resolve_settings_group(self, section_id, group_key)

    def _resolve_settings_member(
        self, section_id: str, group_key: str, member_key: str
    ):
        return settings_navigation.resolve_settings_member(
            self, section_id, group_key, member_key
        )

    def _run_settings_member(
        self, section_id: str, group_key: str, member_key: str
    ) -> None:
        settings_navigation.run_settings_member(
            self, section_id, group_key, member_key
        )

    def _show_help(self) -> None:
        ui_manager = self._ui_manager()
        if ui_manager is not None:
            ui_manager.dialogs.show_help_dialog()

    def _open_session_picker(self) -> None:
        platform_actions.open_session_picker(self)

    def _show_find_action(self) -> None:
        platform_actions.show_find_action(self)

    def _show_contextual_palette(self) -> None:
        """F1: open Find Action, preferably filtered to the focused chrome topic."""
        platform_actions.show_contextual_palette(self)

    def _register_platform_actions(self) -> None:
        platform_actions.register_platform_actions(self)

    def refresh_platform_action_targets(self) -> None:
        """Re-bind reveal targets once host chrome (e.g. Add-tab) exists."""
        platform_actions.refresh_platform_action_targets(self)

    def _resync_action_shortcuts(self) -> None:
        platform_actions.resync_action_shortcuts(self)

    def _quit(self) -> None:
        platform_actions.quit_app(self)

    def _undo(self) -> None:
        dispatcher = getattr(self._window.store, "get_dispatcher", lambda: None)()
        if dispatcher is not None and dispatcher.can_undo():
            dispatcher.undo()

    def _redo(self) -> None:
        dispatcher = getattr(self._window.store, "get_dispatcher", lambda: None)()
        if dispatcher is not None and dispatcher.can_redo():
            dispatcher.redo()