from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from resources.translations import tr, translation_events
from sli_ui_toolkit import TitleBarMenu, TitleBarMenuStrip, TitleBarPresets, WindowControlsConfig
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

logger = logging.getLogger("ImproveImgSLI")


class MainWindowMenuController:
    """Host-level title bar menus (File, Help)."""

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._menu_strip: TitleBarMenuStrip | None = None
        self._find_action_shortcut = None
        self._contextual_palette_shortcut = None
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

    def _file_context_entries(self) -> list[object]:
        return [
            ContextMenuAction(
                "file.new_session",
                self._tr("menu.new_session", "New Session"),
            ),
            # Open/Save project stay wired in handlers but hidden until project IO is ready.
            ContextMenuAction(
                "file.open_project",
                self._tr("menu.open_project", "Open Project"),
                visible=False,
            ),
            ContextMenuAction(
                "file.save_project",
                self._tr("menu.save_project", "Save Project"),
                visible=False,
            ),
            ContextMenuAction(
                "file.settings",
                self._tr("menu.settings", "Settings"),
            ),
            ContextMenuAction(
                "file.quit",
                self._tr("menu.quit", "Quit"),
            ),
        ]

    def _help_context_entries(self) -> list[object]:
        return [
            ContextMenuAction(
                "help.show",
                self._tr("menu.show_help", "Show Help"),
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "help.find_action",
                self._tr("menu.find_action", "Find Action"),
                shortcut="Ctrl+Shift+P",
            ),
        ]

    def _on_language_changed(self, _lang: str) -> None:
        strip = self._menu_strip
        if strip is None:
            return
        language = self._language()
        strip.set_menu_labels(
            [tr("menu.file", language), tr("menu.help", language)]
        )
        # Rebuild entries on next open by replacing the strip on the title bar.
        title_bar = getattr(self._window, "_custom_title_bar", None)
        if title_bar is not None:
            new_strip = self.build_menus()
            self._menu_strip = new_strip
            title_bar.set_menu_strip(new_strip)
            self._register_platform_actions()

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
            "file.settings": self._show_settings,
            "file.quit": self._quit,
        }
        handler = handlers.get(action_id)
        if handler is not None:
            handler()

    def _new_session(self) -> None:
        workspace = self._workspace()
        if workspace is None:
            return
        try:
            workspace.create_workspace_session("image_compare", activate=True)
        except Exception:
            logger.exception("Failed to create workspace session from host menu")

    def _open_project(self) -> None:
        window = self._window
        path, _ = QFileDialog.getOpenFileName(
            window,
            self._tr("menu.open_project", "Open Project"),
            "",
            self._tr("menu.project_filter", "Improve ImgSLI Project (*.imgsli-project)"),
        )
        if not path:
            return
        try:
            from services.io.project_io import load_project_file
            from tabs.registry import TabRegistry

            presenter = self._presenter()
            controller = getattr(presenter, "main_controller", None) if presenter else None
            if controller is None:
                return
            load_project_file(
                path,
                controller.workspace,
                window.store,
                TabRegistry(),
            )
        except Exception:
            logger.exception("Open project failed")

    def _save_project(self) -> None:
        window = self._window
        path, _ = QFileDialog.getSaveFileName(
            window,
            self._tr("menu.save_project", "Save Project"),
            "",
            self._tr("menu.project_filter", "Improve ImgSLI Project (*.imgsli-project)"),
        )
        if not path:
            return
        if not path.endswith(".imgsli-project"):
            path = f"{path}.imgsli-project"
        try:
            from services.io.project_io import save_project_file
            from tabs.registry import TabRegistry

            save_project_file(path, window.store, TabRegistry())
        except Exception:
            logger.exception("Save project failed")

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
        """Group fieldset widget for Find Action reveal after Settings is shown."""
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
            return resolve(group_key)
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
        """Tagged control inside a group for Find Action reveal after Settings is shown."""
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
            return resolve(group_key, member_key)
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
        """Apply a Settings member from Find Action Enter without showing the dialog."""
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

    def _new_image_compare_session(self) -> None:
        workspace = self._workspace()
        if workspace is None:
            return
        try:
            workspace.create_workspace_session("image_compare", activate=True)
        except Exception:
            logger.exception("Failed to create image_compare session from Find Action")

    def _new_multi_compare_session(self) -> None:
        workspace = self._workspace()
        if workspace is None:
            return
        try:
            workspace.create_workspace_session("multi_compare", activate=True)
        except Exception:
            logger.exception("Failed to create multi_compare session from Find Action")

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
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE
        from ui.actions.platform import register_platform_actions

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

        def _picker_page():
            host_ui = getattr(self._presenter(), "ui", None) if self._presenter() else None
            if host_ui is None:
                host_ui = getattr(self._window, "ui", None)
            registry = getattr(host_ui, "_tab_registry", None) if host_ui is not None else None
            if registry is None:
                return None
            return registry.get_page(INITIAL_WORKSPACE_SESSION_TYPE)

        def _resolve_picker_card(session_type: str):
            page = _picker_page()
            card_for = getattr(page, "card_for", None) if page is not None else None
            if not callable(card_for):
                return None
            return card_for(session_type)

        open_picker_target = (
            ActionTarget(widget=add_tab_btn) if add_tab_btn is not None else None
        )
        image_compare_target = ActionTarget(
            ensure_visible=self._open_session_picker,
            resolve_widget=lambda: _resolve_picker_card("image_compare"),
        )
        multi_compare_target = ActionTarget(
            ensure_visible=self._open_session_picker,
            resolve_widget=lambda: _resolve_picker_card("multi_compare"),
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
            new_image_compare=self._new_image_compare_session,
            new_multi_compare=self._new_multi_compare_session,
            file_menu_button=file_btn,
            help_menu_button=help_btn,
            open_session_picker_target=open_picker_target,
            new_image_compare_target=image_compare_target,
            new_multi_compare_target=multi_compare_target,
        )

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
