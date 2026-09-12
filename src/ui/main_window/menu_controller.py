"""Host-level title bar menus (File, Help) and platform action runners."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QWidget

from resources.translations import tr, translation_events
from sli_ui_toolkit import TitleBarMenu, TitleBarMenuStrip, TitleBarPresets, WindowControlsConfig
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
from ui.main_window.project_io import (
    MainWindowProjectIo,
    resolve_session_picker_host_chrome,
)

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

logger = logging.getLogger("ImproveImgSLI")


class MainWindowMenuController:
    """Host-level title bar menus (File, Help).

    Project open/save lives in :class:`MainWindowProjectIo` (``self.project_io``).
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._menu_strip: TitleBarMenuStrip | None = None
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
            menus=strip,
            controls=WindowControlsConfig(
                minimize_icon=AppIcon.MINIMIZE,
                maximize_icon=AppIcon.MAXIMIZE,
                restore_icon=AppIcon.RESTORE,
                close_icon=AppIcon.WINDOW_CLOSE,
            ),
        )
        bar.attach_window(window)
        self._register_platform_actions()
        self._resync_action_shortcuts()
        return bar

    def _app_icon(self):
        from PySide6.QtGui import QIcon

        from utils.resource_loader import resource_path

        return QIcon(resource_path("resources/icons/icon.png"))

    def build_menus(self) -> TitleBarMenuStrip:
        language = self._language()
        parent = self._window if isinstance(self._window, QWidget) else None
        return TitleBarMenuStrip(
            [
                TitleBarMenu(
                    label=tr("menu.file", language),
                    icon=self._app_icon(),
                    entries=self._file_context_entries(),
                    on_triggered=self._on_file_action,
                ),
                TitleBarMenu(
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
            ),
            ContextMenuAction(
                action_id="help.find_action",
                text=self._tr("menu.find_action", "Find Action…"),
                shortcut=self._menu_shortcut("platform.find_action", "Ctrl+Shift+P"),
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
            title_bar.set_menu_strip(new_strip)
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
        ui_manager = self._ui_manager()
        if ui_manager is not None:
            ui_manager.dialogs.show_settings_dialog()

    def _show_settings_section(self, section_id: str) -> None:
        ui_manager = self._ui_manager()
        if ui_manager is not None:
            ui_manager.dialogs.show_settings_dialog(section_id=section_id)

    def _resolve_settings_sidebar(self, section_id: str):
        """Sidebar row widget for Find Action reveal after Settings is shown."""
        ui_manager = self._ui_manager()
        if ui_manager is None:
            return None
        dialog = ui_manager.dialogs.settings_dialog
        if dialog is None:
            return None
        resolve = getattr(dialog, "sidebar_row_widget_for", None)
        if not callable(resolve):
            return None
        try:
            return resolve(section_id)
        except Exception:
            logger.exception(
                "Failed to resolve Settings sidebar row for section %s", section_id
            )
            return None

    def _resolve_settings_group(self, section_id: str, group_key: str):
        ui_manager = self._ui_manager()
        if ui_manager is None:
            return None
        dialog = ui_manager.dialogs.settings_dialog
        if dialog is None:
            return None
        resolve = getattr(dialog, "group_widget_for", None)
        if not callable(resolve):
            return None
        try:
            return resolve(section_id, group_key)
        except Exception:
            logger.exception(
                "Failed to resolve Settings group %s on section %s",
                group_key,
                section_id,
            )
            return None

    def _resolve_settings_member(
        self, section_id: str, group_key: str, member_key: str
    ):
        ui_manager = self._ui_manager()
        if ui_manager is None:
            return None
        dialog = ui_manager.dialogs.settings_dialog
        if dialog is None:
            return None
        resolve = getattr(dialog, "member_widget_for", None)
        if not callable(resolve):
            return None
        try:
            return resolve(section_id, group_key, member_key)
        except Exception:
            logger.exception(
                "Failed to resolve Settings member %s in group %s on section %s",
                member_key,
                group_key,
                section_id,
            )
            return None

    def _run_settings_member(
        self, section_id: str, group_key: str, member_key: str
    ) -> None:
        ui_manager = self._ui_manager()
        if ui_manager is None:
            return
        apply_member = getattr(ui_manager.dialogs, "apply_settings_member", None)
        if not callable(apply_member):
            return
        try:
            apply_member(section_id, group_key, member_key)
        except Exception:
            logger.exception(
                "Failed to run Settings member %s in group %s on section %s",
                member_key,
                group_key,
                section_id,
            )

    def _show_help(self) -> None:
        ui_manager = self._ui_manager()
        if ui_manager is not None:
            ui_manager.dialogs.show_help_dialog()

    def _open_session_picker(self) -> None:
        presenter = self._presenter()
        if presenter is None:
            return
        try:
            from ui.presenters.main_window.workspace import ensure_session_picker_visible

            ensure_session_picker_visible(presenter)
        except Exception:
            logger.exception("Failed to open session picker from Find Action")

    def _show_find_action(self) -> None:
        from ui.actions.palette import show_command_palette

        show_command_palette(parent=self._window)

    def _show_contextual_palette(self) -> None:
        """F1: open Find Action, preferably filtered to the focused chrome topic."""
        from PySide6.QtWidgets import QApplication

        from tabs.registry import get_shared_tab_registry
        from ui.actions.palette import show_command_palette
        from ui.actions.registry import get_action_registry

        active_tab = None
        try:
            tab = get_shared_tab_registry().get_active_tab()
            active_tab = getattr(tab, "session_type", None) if tab is not None else None
        except Exception:
            active_tab = None

        focused = QApplication.focusWidget()
        match = get_action_registry().find_for_widget(
            focused,
            active_tab=active_tab,
        )
        topic = match.topic if match is not None else None
        preselect = match.action_id if match is not None else None
        show_command_palette(
            topic=topic,
            preselect_action_id=preselect,
            parent=self._window,
            auto_pulse=match is not None,
        )

    def _register_platform_actions(self) -> None:
        from core.actions.types import ActionTarget
        from ui.actions.platform import register_platform_actions
        from ui.actions.workspace_new_sessions import (
            image_compare_runner,
            image_compare_target,
            multi_compare_runner,
            multi_compare_target,
        )

        file_btn = help_btn = None
        strip = self._menu_strip
        if strip is not None:
            buttons = strip.buttons()
            if len(buttons) >= 1:
                file_btn = buttons[0]
            if len(buttons) >= 2:
                help_btn = buttons[1]

        add_tab_btn = None
        ui = getattr(self._presenter(), "ui", None) if self._presenter() else None
        if ui is None:
            ui = getattr(self._window, "ui", None)
        if ui is not None:
            add_tab_btn = getattr(ui, "btn_new_session", None)

        def _resolve_picker_card(session_type: str):
            chrome = resolve_session_picker_host_chrome()
            if chrome is None:
                return None
            return chrome.card_for(session_type)

        open_picker_target = (
            ActionTarget(widget=add_tab_btn) if add_tab_btn is not None else None
        )

        register_platform_actions(
            show_settings=self._show_settings,
            show_help=self._show_help,
            new_session=self._new_session,
            show_find_action=self._show_find_action,
            quit_app=self._quit,
            show_contextual_palette=self._show_contextual_palette,
            show_settings_section=self._show_settings_section,
            resolve_settings_sidebar=self._resolve_settings_sidebar,
            resolve_settings_group=self._resolve_settings_group,
            resolve_settings_member=self._resolve_settings_member,
            run_settings_member=self._run_settings_member,
            open_session_picker=self._open_session_picker,
            new_image_compare=image_compare_runner(self._create_workspace_session),
            new_multi_compare=multi_compare_runner(self._create_workspace_session),
            open_project=self._open_project,
            save_project=self._save_project,
            save_project_as=self._save_project_as,
            file_menu_button=file_btn,
            help_menu_button=help_btn,
            open_session_picker_target=open_picker_target,
            new_image_compare_target=image_compare_target(
                ensure_visible=self._open_session_picker,
                resolve_card=_resolve_picker_card,
            ),
            new_multi_compare_target=multi_compare_target(
                ensure_visible=self._open_session_picker,
                resolve_card=_resolve_picker_card,
            ),
        )
        self._wire_session_picker_recent()

    def refresh_platform_action_targets(self) -> None:
        """Re-bind reveal targets once host chrome (e.g. Add-tab) exists."""
        self._register_platform_actions()
        self._resync_action_shortcuts()

    def _resync_action_shortcuts(self) -> None:
        from ui.actions.binder import resync_action_shortcuts

        resync_action_shortcuts(self._window)

    def _quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
