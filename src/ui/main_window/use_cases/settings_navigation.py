"""Settings-dialog opening and Find-Action deep-link widget resolution for
``MainWindowMenuController`` -- split out to keep that class down to the
menu-building job itself (mirrors the ``use_cases`` split, see
docs/dev/CODE_PATTERNS.md). Every function here takes the menu controller as
its first argument.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


def show_settings(controller) -> None:
    ui_manager = controller._ui_manager()
    if ui_manager is not None:
        ui_manager.dialogs.show_settings_dialog()


def show_settings_section(controller, section_id: str) -> None:
    ui_manager = controller._ui_manager()
    if ui_manager is not None:
        ui_manager.dialogs.show_settings_dialog(section_id=section_id)


def resolve_settings_sidebar(controller, section_id: str):
    """Sidebar row widget for Find Action reveal after Settings is shown."""
    ui_manager = controller._ui_manager()
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


def resolve_settings_group(controller, section_id: str, group_key: str):
    ui_manager = controller._ui_manager()
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


def resolve_settings_member(
    controller, section_id: str, group_key: str, member_key: str
):
    ui_manager = controller._ui_manager()
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


def run_settings_member(
    controller, section_id: str, group_key: str, member_key: str
) -> None:
    ui_manager = controller._ui_manager()
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