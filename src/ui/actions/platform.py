"""Register host/platform actions into the action catalog."""

from __future__ import annotations

from collections.abc import Callable

from core.actions.types import ActionDescriptor, ActionTarget
from ui.actions.registry import ActionRegistry, get_action_registry

_BC_WORKSPACE = "action.breadcrumb.workspace"


def register_settings_page_actions(
    *,
    show_settings_section: Callable[[str], None],
    registry: ActionRegistry | None = None,
    resolve_settings_sidebar: Callable[[str], object | None] | None = None,
    resolve_settings_group: Callable[[str, str], object | None] | None = None,
    resolve_settings_member: Callable[[str, str, str], object | None] | None = None,
    run_settings_member: Callable[[str, str, str], None] | None = None,
) -> None:
    """Delegate to Settings-owned auto-contribution (``plugins.settings.actions``)."""
    from plugins.settings.actions import contribute_settings_actions

    contribute_settings_actions(
        show_settings_section=show_settings_section,
        registry=registry,
        resolve_settings_sidebar=resolve_settings_sidebar,
        resolve_settings_group=resolve_settings_group,
        resolve_settings_member=resolve_settings_member,
        run_settings_member=run_settings_member,
    )


def register_platform_actions(
    *,
    show_settings: Callable[[], None],
    show_help: Callable[[], None],
    new_session: Callable[[], None],
    show_find_action: Callable[[], None],
    quit_app: Callable[[], None],
    show_contextual_palette: Callable[[], None] | None = None,
    show_settings_section: Callable[[str], None] | None = None,
    resolve_settings_sidebar: Callable[[str], object | None] | None = None,
    resolve_settings_group: Callable[[str, str], object | None] | None = None,
    resolve_settings_member: Callable[[str, str, str], object | None] | None = None,
    run_settings_member: Callable[[str, str, str], None] | None = None,
    open_session_picker: Callable[[], None] | None = None,
    new_image_compare: Callable[[], None] | None = None,
    new_multi_compare: Callable[[], None] | None = None,
    paste_clipboard_image: Callable[[], None] | None = None,
    open_project: Callable[[], None] | None = None,
    save_project: Callable[[], None] | None = None,
    save_project_as: Callable[[], None] | None = None,
    file_menu_button: object | None = None,
    help_menu_button: object | None = None,
    open_session_picker_target: ActionTarget | None = None,
    new_image_compare_target: ActionTarget | None = None,
    new_multi_compare_target: ActionTarget | None = None,
    registry: ActionRegistry | None = None,
) -> None:
    reg = registry if registry is not None else get_action_registry()
    contextual = show_contextual_palette or show_find_action
    section_runner = show_settings_section or (lambda _sid: show_settings())

    def _menu_target(button: object | None, menu_action_id: str) -> ActionTarget | None:
        if button is None:
            return None
        return ActionTarget(widget=button, menu_action_id=menu_action_id)

    def _default_paste() -> None:
        from plugins.export.events import ExportPasteImageFromClipboardEvent
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        event_bus = None
        if app is not None:
            for widget in app.topLevelWidgets():
                presenter = getattr(widget, "presenter", None)
                event_bus = getattr(presenter, "event_bus", None) if presenter else None
                if event_bus is None and presenter is not None:
                    controller = getattr(presenter, "main_controller", None)
                    event_bus = getattr(controller, "event_bus", None)
                if event_bus is not None:
                    break
        if event_bus is not None:
            event_bus.emit(ExportPasteImageFromClipboardEvent())

    paste_runner = paste_clipboard_image or _default_paste

    file_settings = _menu_target(file_menu_button, "file.settings")
    file_new = _menu_target(file_menu_button, "file.new_session")
    file_open_project = _menu_target(file_menu_button, "file.open_project")
    file_save_project = _menu_target(file_menu_button, "file.save_project")
    file_save_project_as = _menu_target(file_menu_button, "file.save_project_as")
    file_quit = _menu_target(file_menu_button, "file.quit")
    help_show = _menu_target(help_menu_button, "help.show")
    help_find = _menu_target(help_menu_button, "help.find_action")

    specs: list[ActionDescriptor] = [
        ActionDescriptor(
            action_id="platform.settings",
            label_key="menu.settings",
            description_key="action.platform.settings_desc",
            breadcrumb=("menu.file", "menu.settings"),
            owner_tab=None,
            topic="settings",
            shortcut="Ctrl+,",
            help_page="settings",
            run=show_settings,
            target=file_settings,
        ),
        ActionDescriptor(
            action_id="platform.help",
            label_key="menu.show_help",
            description_key="action.platform.help_desc",
            breadcrumb=("menu.help", "menu.show_help"),
            owner_tab=None,
            topic="help",
            shortcut="Ctrl+F1",
            help_page="introduction",
            run=show_help,
            target=help_show,
        ),
        ActionDescriptor(
            action_id="platform.new_session",
            label_key="menu.new_session",
            description_key="action.platform.new_session_desc",
            breadcrumb=("menu.file", "menu.new_session"),
            owner_tab=None,
            topic="workspace",
            shortcut="Ctrl+N",
            help_page="file_management",
            run=new_session,
            target=file_new,
        ),
        ActionDescriptor(
            action_id="platform.find_action",
            label_key="menu.find_action",
            description_key="action.platform.find_action_desc",
            breadcrumb=("menu.help", "menu.find_action"),
            owner_tab=None,
            topic="discovery",
            shortcut="Ctrl+Shift+P",
            help_page="hotkeys",
            run=show_find_action,
            target=help_find,
        ),
        ActionDescriptor(
            action_id="platform.find_action_context",
            label_key="action.platform.find_action_context",
            description_key="action.platform.find_action_context_desc",
            breadcrumb=("menu.help", "menu.find_action"),
            owner_tab=None,
            topic="discovery",
            shortcut="F1",
            help_page="hotkeys",
            run=contextual,
            target=help_find,
        ),
        ActionDescriptor(
            action_id="platform.paste_clipboard_image",
            label_key="action.platform.paste_clipboard_image",
            description_key="action.platform.paste_clipboard_image_desc",
            breadcrumb=("menu.file",),
            owner_tab=None,
            topic="session",
            shortcut="Ctrl+V",
            help_page="file_management",
            run=paste_runner,
            target=None,
        ),
        ActionDescriptor(
            action_id="platform.quit",
            label_key="menu.quit",
            description_key="action.platform.quit_desc",
            breadcrumb=("menu.file", "menu.quit"),
            owner_tab=None,
            topic="app",
            shortcut="Ctrl+Q",
            run=quit_app,
            target=file_quit,
        ),
    ]
    if open_project is not None:
        specs.insert(
            3,
            ActionDescriptor(
                action_id="platform.open_project",
                label_key="menu.open_project",
                description_key="action.platform.open_project_desc",
                breadcrumb=("menu.file", "menu.open_project"),
                owner_tab=None,
                topic="workspace",
                shortcut="Ctrl+Shift+O",
                help_page="file_management",
                run=open_project,
                target=file_open_project,
            ),
        )
    if save_project is not None:
        specs.insert(
            4 if open_project is not None else 3,
            ActionDescriptor(
                action_id="platform.save_project",
                label_key="menu.save_project",
                description_key="action.platform.save_project_desc",
                breadcrumb=("menu.file", "menu.save_project"),
                owner_tab=None,
                topic="workspace",
                shortcut="Shift+S",
                help_page="file_management",
                run=save_project,
                target=file_save_project,
            ),
        )
    if save_project_as is not None:
        insert_at = 3
        if open_project is not None:
            insert_at += 1
        if save_project is not None:
            insert_at += 1
        specs.insert(
            insert_at,
            ActionDescriptor(
                action_id="platform.save_project_as",
                label_key="menu.save_project_as",
                description_key="action.platform.save_project_as_desc",
                breadcrumb=("menu.file", "menu.save_project_as"),
                owner_tab=None,
                topic="workspace",
                shortcut="Ctrl+Shift+S",
                help_page="file_management",
                run=save_project_as,
                target=file_save_project_as,
            ),
        )
    if open_session_picker is not None:
        specs.append(
            ActionDescriptor(
                action_id="workspace.open_session_picker",
                label_key="action.workspace.open_session_picker",
                description_key="action.workspace.open_session_picker_desc",
                breadcrumb=(_BC_WORKSPACE,),
                owner_tab=None,
                topic="workspace",
                help_page="file_management",
                run=open_session_picker,
                target=open_session_picker_target,
            )
        )
    if new_image_compare is not None:
        specs.append(
            ActionDescriptor(
                action_id="workspace.new_image_compare",
                label_key="action.workspace.new_image_compare",
                description_key="action.workspace.new_image_compare_desc",
                breadcrumb=(_BC_WORKSPACE,),
                owner_tab=None,
                topic="workspace",
                help_page="file_management",
                run=new_image_compare,
                target=new_image_compare_target,
            )
        )
    if new_multi_compare is not None:
        specs.append(
            ActionDescriptor(
                action_id="workspace.new_multi_compare",
                label_key="action.workspace.new_multi_compare",
                description_key="action.workspace.new_multi_compare_desc",
                breadcrumb=(_BC_WORKSPACE,),
                owner_tab=None,
                topic="workspace",
                help_page="file_management",
                run=new_multi_compare,
                target=new_multi_compare_target,
            )
        )
    for action in specs:
        reg.register(action)

    register_settings_page_actions(
        show_settings_section=section_runner,
        registry=reg,
        resolve_settings_sidebar=resolve_settings_sidebar,
        resolve_settings_group=resolve_settings_group,
        resolve_settings_member=resolve_settings_member,
        run_settings_member=run_settings_member,
    )


def contribute_platform_keymap_defaults(registry) -> None:
    """Metadata defaults for platform / workspace actions (Settings → Keyboard)."""
    from ui.actions.keymap import KeymapDefaultEntry

    entries = (
        KeymapDefaultEntry(
            "platform.settings",
            "menu.settings",
            "Ctrl+,",
            None,
            ("menu.file",),
            description_key="action.platform.settings_desc",
        ),
        KeymapDefaultEntry(
            "platform.help",
            "menu.show_help",
            "Ctrl+F1",
            None,
            ("menu.help",),
            description_key="action.platform.help_desc",
        ),
        KeymapDefaultEntry(
            "platform.new_session",
            "menu.new_session",
            "Ctrl+N",
            None,
            ("menu.file",),
            description_key="action.platform.new_session_desc",
        ),
        KeymapDefaultEntry(
            "platform.open_project",
            "menu.open_project",
            "Ctrl+Shift+O",
            None,
            ("menu.file",),
            description_key="action.platform.open_project_desc",
        ),
        KeymapDefaultEntry(
            "platform.save_project",
            "menu.save_project",
            "Shift+S",
            None,
            ("menu.file",),
            description_key="action.platform.save_project_desc",
        ),
        KeymapDefaultEntry(
            "platform.save_project_as",
            "menu.save_project_as",
            "Ctrl+Shift+S",
            None,
            ("menu.file",),
            description_key="action.platform.save_project_as_desc",
        ),
        KeymapDefaultEntry(
            "platform.find_action",
            "menu.find_action",
            "Ctrl+Shift+P",
            None,
            ("menu.help",),
            description_key="action.platform.find_action_desc",
        ),
        KeymapDefaultEntry(
            "platform.find_action_context",
            "action.platform.find_action_context",
            "F1",
            None,
            ("menu.help",),
            description_key="action.platform.find_action_context_desc",
        ),
        KeymapDefaultEntry(
            "platform.paste_clipboard_image",
            "action.platform.paste_clipboard_image",
            "Ctrl+V",
            None,
            ("menu.file",),
            description_key="action.platform.paste_clipboard_image_desc",
        ),
        KeymapDefaultEntry(
            "platform.quit",
            "menu.quit",
            "Ctrl+Q",
            None,
            ("menu.file",),
            description_key="action.platform.quit_desc",
        ),
        KeymapDefaultEntry(
            "workspace.open_session_picker",
            "action.workspace.open_session_picker",
            None,
            None,
            ("action.breadcrumb.workspace",),
            description_key="action.workspace.open_session_picker_desc",
        ),
        KeymapDefaultEntry(
            "workspace.new_image_compare",
            "action.workspace.new_image_compare",
            None,
            None,
            ("action.breadcrumb.workspace",),
            description_key="action.workspace.new_image_compare_desc",
        ),
        KeymapDefaultEntry(
            "workspace.new_multi_compare",
            "action.workspace.new_multi_compare",
            None,
            None,
            ("action.breadcrumb.workspace",),
            description_key="action.workspace.new_multi_compare_desc",
        ),
    )
    for entry in entries:
        registry.register(entry)
