from __future__ import annotations

import logging

from PySide6.QtCore import QPoint

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from resources.translations import tr
from shared_toolkit.ui.text_input_dialog import AppTextInputDialog
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuSeparator,
)
from ui.context_menu.manager import open_context_menu_entries
from ui.presenters.main_window.workspace import (
    on_workspace_tab_close_requested,
)

logger = logging.getLogger("ImproveImgSLI")

_SESSION_TITLE_KEY_TEMPLATES = (
    "workspace.session_types.{session_type}",
    "session_picker.types.{session_type}",
)


def on_workspace_tab_context_menu_requested(
    presenter, index: int, global_pos: QPoint
) -> None:
    if index < 0:
        return
    entries = build_workspace_tab_context_menu_entries(presenter, index)
    if not entries:
        return
    parent = getattr(presenter.ui, "main_window", None)
    if parent is None:
        return

    def on_triggered(action_id: str, data: object) -> None:
        handle_workspace_tab_context_action(presenter, index, action_id, data)

    open_context_menu_entries(
        source_widget=parent,
        global_pos=global_pos,
        entries=tuple(entries),
        key=("workspace-tab", index),
        on_triggered=on_triggered,
    )


def build_workspace_tab_context_menu_entries(presenter, index: int) -> list[object]:
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not session_id:
        return []

    session = (
        presenter.session_manager.get_session(session_id)
        if presenter.session_manager is not None
        else None
    )
    session_type = getattr(session, "session_type", None)
    language = _language(presenter)
    entries: list[object] = [
        ContextMenuAction(
            "workspace.tab.close",
            _tr("workspace.tab_menu.close", "Close Tab", language),
        ),
        ContextMenuAction(
            "workspace.tab.rename",
            _tr("workspace.tab_menu.rename", "Rename Tab", language),
        ),
    ]

    if session_type not in (None, INITIAL_WORKSPACE_SESSION_TYPE):
        entries.append(
            ContextMenuAction(
                "workspace.tab.duplicate",
                _tr("workspace.tab_menu.duplicate", "Duplicate Tab", language),
            )
        )

    session_count = (
        len(presenter.session_manager.list_sessions())
        if presenter.session_manager is not None
        else 0
    )
    if session_count > 1:
        entries.append(
            ContextMenuAction(
                "workspace.tab.close_others",
                _tr("workspace.tab_menu.close_others", "Close Other Tabs", language),
            )
        )

    new_entries = _new_session_menu_entries(presenter, language)
    if new_entries:
        entries.append(ContextMenuSeparator())
        entries.append(
            ContextMenuAction(
                "workspace.tab.new",
                _tr("workspace.tab_menu.new", "New Tab", language),
                children=tuple(new_entries),
            )
        )
    return entries


def handle_workspace_tab_context_action(
    presenter, index: int, action_id: str, data: object
) -> None:
    if action_id == "workspace.tab.rename":
        _rename_workspace_tab(presenter, index)
        return

    if not presenter.main_controller:
        return

    if action_id == "workspace.tab.close":
        on_workspace_tab_close_requested(presenter, index)
        return

    if action_id == "workspace.tab.duplicate":
        session_id = presenter.ui.workspace_tabs.tabData(index)
        if not session_id:
            return
        tab_registry = getattr(presenter.ui, "_tab_registry", None)
        try:
            presenter.main_controller.workspace.duplicate_workspace_session(
                session_id,
                activate=True,
                tab_registry=tab_registry,
            )
        except Exception:
            logger.exception("workspace tab duplicate failed for %s", session_id)
        return

    if action_id == "workspace.tab.close_others":
        _close_other_workspace_tabs(presenter, index)
        return

    if action_id.startswith("workspace.tab.new."):
        session_type = data
        if not session_type:
            session_type = action_id.removeprefix("workspace.tab.new.")
        try:
            presenter.main_controller.workspace.create_workspace_session(
                str(session_type),
                activate=True,
            )
        except Exception:
            logger.exception(
                "workspace tab new-session failed for %s", session_type
            )


def _rename_workspace_tab(presenter, index: int) -> None:
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not session_id or presenter.session_manager is None:
        return
    session = presenter.session_manager.get_session(session_id)
    if session is None:
        return

    language = _language(presenter)
    display_title = _session_display_title(presenter, session, index, language)

    parent = getattr(presenter.ui, "main_window", None)
    text, ok = AppTextInputDialog.get_text(
        parent,
        _tr("workspace.tab_menu.rename", "Rename Tab", language),
        _tr("workspace.tab_menu.rename_prompt", "Name", language),
        display_title,
        ok_text=_tr("common.ok", "OK", language),
        cancel_text=_tr("common.cancel", "Cancel", language),
    )
    if not ok:
        return

    stored = _title_for_storage(presenter, session, text, language, display_title)
    if stored == (getattr(session, "title", "") or ""):
        return
    try:
        presenter.session_manager.rename_session(session_id, stored)
    except Exception:
        logger.exception("workspace tab rename failed for %s", session_id)


def _session_display_title(presenter, session, index: int, language: str) -> str:
    """Label shown on the tab strip / rename field (may be localized)."""
    tab_text = presenter.ui.workspace_tabs.tabText(index)
    if tab_text:
        return tab_text
    localize = getattr(presenter.ui, "_localized_session_title", None)
    if callable(localize):
        return localize(session, language)
    return getattr(session, "title", "") or ""


def _title_for_storage(
    presenter,
    session,
    edited: str,
    language: str,
    display_title: str,
) -> str:
    """Map rename-dialog text back to the language-agnostic store value.

    Auto titles stay canonical (``Session Picker``). Only a real user rename
    is stored as-is; confirming the localized default must not freeze a
    translation into ``session.title``.
    """
    from domain.workspace import WorkspaceState

    text = edited.strip()
    raw = getattr(session, "title", "") or ""
    session_type = getattr(session, "session_type", "") or ""
    if not text:
        return raw

    # Unchanged from what we showed — keep whatever is already in the store.
    if text == display_title.strip():
        return raw

    if not WorkspaceState.is_auto_title(raw, session_type):
        return text

    type_label = _session_type_display_label(presenter, session_type, language)
    prefix = WorkspaceState.default_title_prefix(session_type)
    # Localized auto label (with or without a legacy number) → bare canonical.
    if text == type_label:
        return prefix
    type_prefix = f"{type_label} "
    if text.startswith(type_prefix) and text[len(type_prefix) :].isdigit():
        return prefix

    return text


def _session_type_display_label(presenter, session_type: str, language: str) -> str:
    localize_type = getattr(presenter.ui, "_localized_session_type_label", None)
    if callable(localize_type):
        return localize_type(session_type, language)
    from domain.workspace import WorkspaceState

    return WorkspaceState.default_title_prefix(session_type)


def _close_other_workspace_tabs(presenter, keep_index: int) -> None:
    tabs = presenter.ui.workspace_tabs
    keep_id = tabs.tabData(keep_index)
    if not keep_id:
        return
    to_close: list[str] = []
    for tab_index in range(tabs.count()):
        if tab_index == keep_index:
            continue
        session_id = tabs.tabData(tab_index)
        if session_id:
            to_close.append(session_id)
    for session_id in to_close:
        presenter.main_controller.workspace.close_workspace_session(session_id)


def _new_session_menu_entries(presenter, language: str) -> list[ContextMenuAction]:
    workspace = (
        presenter.main_controller.workspace
        if presenter.main_controller is not None
        else None
    )
    if workspace is None:
        return []
    try:
        blueprints = list(workspace.list_session_blueprints())
    except Exception:
        logger.exception("list_session_blueprints failed for workspace tab menu")
        return []

    entries: list[ContextMenuAction] = []
    for blueprint in blueprints:
        session_type = blueprint.session_type
        if session_type == INITIAL_WORKSPACE_SESSION_TYPE:
            continue
        fallback = blueprint.resolved_title() or session_type
        label = _localized_session_type_label(session_type, fallback, language)
        entries.append(
            ContextMenuAction(
                f"workspace.tab.new.{session_type}",
                label,
                data=session_type,
            )
        )
    return entries


def _localized_session_type_label(
    session_type: str, fallback: str, language: str
) -> str:
    for template in _SESSION_TITLE_KEY_TEMPLATES:
        key = template.format(session_type=session_type)
        label = tr(key, language)
        if label != key:
            return label
    return fallback


def _language(presenter) -> str:
    try:
        return presenter.store.settings.current_language
    except AttributeError:
        return "en"


def _tr(key: str, fallback: str, language: str) -> str:
    translated = tr(key, language)
    return fallback if translated == key else translated
