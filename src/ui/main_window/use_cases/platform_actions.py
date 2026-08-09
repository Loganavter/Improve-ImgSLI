"""Global command-palette / platform-action-registry wiring and keyboard
shortcut resync for ``MainWindowMenuController`` -- split out to keep that
class down to the menu-building job itself (mirrors the ``use_cases``
split, see docs/dev/CODE_PATTERNS.md). Every function here takes the menu
controller as its first argument.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

logger = logging.getLogger("ImproveImgSLI")


def open_session_picker(controller) -> None:
    presenter = controller._presenter()
    if presenter is None:
        return
    try:
        from ui.presenters.main_window.workspace import ensure_session_picker_visible

        ensure_session_picker_visible(presenter)
    except Exception:
        logger.exception("Failed to open session picker from Find Action")


def show_find_action(controller) -> None:
    from ui.actions.palette import show_command_palette

    show_command_palette(parent=controller._window)


def show_contextual_palette(controller) -> None:
    """F1: open Find Action, preferably filtered to the focused chrome topic."""
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
        parent=controller._window,
        auto_pulse=match is not None,
    )


def register_platform_actions(controller) -> None:
    from core.actions.types import ActionTarget
    from ui.actions.platform import register_platform_actions as _register
    from ui.actions.workspace_new_sessions import (
        image_compare_runner,
        image_compare_target,
        multi_compare_runner,
        multi_compare_target,
    )
    from ui.main_window.project_io import resolve_session_picker_host_chrome

    file_btn = help_btn = None
    strip = controller._menu_strip
    if strip is not None:
        buttons = strip.buttons()
        if len(buttons) >= 1:
            file_btn = buttons[0]
        if len(buttons) >= 2:
            help_btn = buttons[1]

    add_tab_btn = None
    ui = getattr(controller._presenter(), "ui", None) if controller._presenter() else None
    if ui is None:
        ui = getattr(controller._window, "ui", None)
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

    _register(
        show_settings=controller._show_settings,
        show_help=controller._show_help,
        new_session=controller._new_session,
        show_find_action=controller._show_find_action,
        quit_app=controller._quit,
        show_contextual_palette=controller._show_contextual_palette,
        show_settings_section=controller._show_settings_section,
        resolve_settings_sidebar=controller._resolve_settings_sidebar,
        resolve_settings_group=controller._resolve_settings_group,
        resolve_settings_member=controller._resolve_settings_member,
        run_settings_member=controller._run_settings_member,
        open_session_picker=controller._open_session_picker,
        new_image_compare=image_compare_runner(controller._create_workspace_session),
        new_multi_compare=multi_compare_runner(controller._create_workspace_session),
        open_project=controller._open_project,
        save_project=controller._save_project,
        save_project_as=controller._save_project_as,
        file_menu_button=file_btn,
        help_menu_button=help_btn,
        open_session_picker_target=open_picker_target,
        new_image_compare_target=image_compare_target(
            ensure_visible=controller._open_session_picker,
            resolve_card=_resolve_picker_card,
        ),
        new_multi_compare_target=multi_compare_target(
            ensure_visible=controller._open_session_picker,
            resolve_card=_resolve_picker_card,
        ),
    )
    controller._wire_session_picker_recent()


def refresh_platform_action_targets(controller) -> None:
    """Re-bind reveal targets once host chrome (e.g. Add-tab) exists."""
    controller._register_platform_actions()
    controller._resync_action_shortcuts()


def resync_action_shortcuts(controller) -> None:
    from ui.actions.binder import resync_action_shortcuts as _resync

    _resync(controller._window)


def quit_app(_controller) -> None:
    app = QApplication.instance()
    if app is not None:
        app.quit()
