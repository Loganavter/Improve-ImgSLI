"""Context menu actions for a recent project card."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QCursor, QDesktopServices
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

from plugins.image_properties.plugin import open_image_properties_dialog
from sli_ui_toolkit.i18n import get_current_language
from sli_ui_toolkit.i18n import tr as app_tr
from services.io.recent_projects import (
    SORT_ASC,
    SORT_CREATED,
    SORT_DESC,
    SORT_MODIFIED,
    SORT_NAME,
    VIEW_GRID,
    VIEW_LIST,
    RecentProjectRecord,
    _snapshot_file_times,
    get_recent_sort_mode,
    get_recent_sort_order,
    get_recent_view_mode,
    normalize_recent_sort_mode,
    set_recent_sort_mode,
    set_recent_sort_order,
    set_recent_view_mode,
)
from tabs.session_picker.icons import Icon as SessionPickerIcon
from tabs.session_picker.recent.cards import format_session_types
from ui.widgets.shelf.relative_time import format_absolute_timestamp
from ui.context_menu.manager import open_context_menu_entries
from core.log_names import APP_LOGGER_NAME


def sort_view_menu_entries(
    translate: Callable[..., str],
    on_prefs_changed: Callable[[], None] | None = None,
) -> list:
    """FM-style "Sort by" + "View" submenu entries for the recent shelf.

    Checkmarks mirror the live persisted prefs (same source the header
    chips read); handlers persist + notify via *on_prefs_changed* so the
    panel refreshes exactly like a header-chip click.
    """
    sort_mode = get_recent_sort_mode()
    sort_order = get_recent_sort_order()
    view_mode = get_recent_view_mode()

    sort_children = tuple(
        ContextMenuAction(
            action_id,
            translate(key, default),
            icon=icon,
            data=mode,
            checkable=True,
            checked=sort_mode == mode,
        )
        for action_id, key, default, mode, icon in (
            ("recent.sort.modified", "recent.sort_modified", "Date modified", SORT_MODIFIED, SessionPickerIcon.SORT_BY_MODIFIED),
            ("recent.sort.created", "recent.sort_created", "Date created", SORT_CREATED, SessionPickerIcon.SORT_BY_CREATED),
            ("recent.sort.name", "recent.sort_name", "Name", SORT_NAME, SessionPickerIcon.SORT_BY_NAME),
        )
    ) + (
        ContextMenuSeparator(),
        ContextMenuAction(
            "recent.sort.asc",
            translate("recent.sort_asc", "Ascending"),
            icon=SessionPickerIcon.SORT_ASC,
            data=SORT_ASC,
            checkable=True,
            checked=sort_order == SORT_ASC,
        ),
        ContextMenuAction(
            "recent.sort.desc",
            translate("recent.sort_desc", "Descending"),
            icon=SessionPickerIcon.SORT_DESC,
            data=SORT_DESC,
            checkable=True,
            checked=sort_order == SORT_DESC,
        ),
    )
    view_children = (
        ContextMenuAction(
            "recent.view.grid",
            translate("recent.view_grid", "Grid"),
            icon=SessionPickerIcon.VIEW_GRID,
            data=VIEW_GRID,
            checkable=True,
            checked=view_mode == VIEW_GRID,
        ),
        ContextMenuAction(
            "recent.view.list",
            translate("recent.view_list", "List"),
            icon=SessionPickerIcon.VIEW_LIST,
            data=VIEW_LIST,
            checkable=True,
            checked=view_mode == VIEW_LIST,
        ),
    )

    return [
        ContextMenuAction(
            "recent.sort_by",
            translate("recent.sort_by", "Sort by"),
            icon=SessionPickerIcon.SORT_BY_MODIFIED,
            children=sort_children,
        ),
        ContextMenuAction(
            "recent.view",
            translate("recent.view", "View"),
            icon=SessionPickerIcon.VIEW_GRID,
            children=view_children,
        ),
    ]


def handle_sort_view_action(
    action_id: str,
    data: object,
    on_prefs_changed: Callable[[], None] | None = None,
) -> bool:
    """Dispatch a Sort by / View submenu action; True when handled."""
    if action_id in ("recent.sort.modified", "recent.sort.created", "recent.sort.name"):
        set_recent_sort_mode(normalize_recent_sort_mode(str(data)))
    elif action_id in ("recent.sort.asc", "recent.sort.desc"):
        set_recent_sort_order(str(data))
    elif action_id in ("recent.view.grid", "recent.view.list"):
        set_recent_view_mode(str(data))
    else:
        return False
    try:
        if on_prefs_changed is not None:
            on_prefs_changed()
    except Exception:
        pass
    return True


def open_recent_project_menu(
    *,
    source_widget,
    record: RecentProjectRecord,
    translate: Callable[..., str],
    on_open: Callable[[RecentProjectRecord], None],
    on_remove: Callable[[RecentProjectRecord], None],
    selected_paths: set[str] | None = None,
    on_remove_selected: Callable[[], None] | None = None,
) -> None:
    missing = not Path(record.path).is_file()
    multi = bool(selected_paths) and len(selected_paths) > 1 and record.path in selected_paths  # type: ignore[arg-type,operator]  # selected_paths guarded by bool()
    entries = [
        ContextMenuAction(
            "recent.open",
            translate("recent.action_open", "Open"),
            icon="folder_open.svg",
            enabled=not missing and not multi,
        ),
        ContextMenuAction(
            "recent.properties",
            translate("recent.action_properties", "Properties"),
            icon="photo.svg",
            enabled=not multi,
        ),
    ]
    if multi and on_remove_selected is not None:
        entries.append(
            ContextMenuAction(
                "recent.remove_selected",
                translate(
                    "recent.action_remove_selected",
                    "Remove selected ({n})",
                ).format(n=len(selected_paths)),  # type: ignore[arg-type]  # selected_paths non-None when multi
                icon="delete.svg",
            )
        )
    else:
        entries.append(
            ContextMenuAction(
                "recent.remove",
                translate("recent.action_remove", "Remove from list"),
                icon="delete.svg",
            )
        )
    entries.extend(
        [
            ContextMenuSeparator(),
            ContextMenuAction(
                "recent.reveal",
                translate("recent.action_reveal", "Show in folder"),
                icon="folder_open.svg",
                enabled=Path(record.path).parent.is_dir() and not multi,
            ),
        ]
    )

    def on_triggered(action_id: str, _data: object) -> None:
        if action_id == "recent.open":
            on_open(record)
        elif action_id == "recent.properties":
            open_recent_project_properties(record, translate=translate, parent=source_widget)
        elif action_id == "recent.remove":
            on_remove(record)
        elif action_id == "recent.remove_selected" and on_remove_selected is not None:
            on_remove_selected()
        elif action_id == "recent.reveal":
            parent = Path(record.path).parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))

    open_context_menu_entries(
        source_widget=source_widget,
        global_pos=QCursor.pos(),
        entries=tuple(entries),
        key=("recent-project", record.path),
        on_triggered=on_triggered,
    )


def open_recent_empty_menu(
    *,
    source_widget,
    global_pos=None,
    translate: Callable[..., str],
    on_prefs_changed: Callable[[], None] | None = None,
) -> None:
    """FM background menu for the empty shelf: Sort by / View submenus."""
    from PySide6.QtGui import QCursor as _QCursor

    entries = sort_view_menu_entries(translate, on_prefs_changed)
    if not entries:
        return

    def on_triggered(action_id: str, data: object) -> None:
        try:
            import logging as _logging

            _logging.getLogger(APP_LOGGER_NAME).debug(
                "[recent-menu] empty menu triggered action=%s data=%r", action_id, data
            )
        except Exception:
            pass
        try:
            handle_sort_view_action(action_id, data, on_prefs_changed)
        except Exception:
            pass

    try:
        pos = global_pos if global_pos is not None else _QCursor.pos()
    except Exception:
        pos = global_pos
    open_context_menu_entries(
        source_widget=source_widget,
        global_pos=pos,
        entries=tuple(entries),
        key=("recent-empty",),
        on_triggered=on_triggered,
    )


def open_recent_project_properties(
    record: RecentProjectRecord,
    *,
    translate: Callable[..., str],
    parent=None,
) -> None:
    """Reuse the shared Image Properties dialog with cached Recent metadata."""
    missing = not Path(record.path).is_file()
    lang = get_current_language() or "en"
    app_rows: list[tuple[str, str, str]] = []
    if missing:
        app_rows.append(
            (
                "recent.prop_status",
                translate("recent.prop_status", "Status"),
                translate("recent.missing", "File missing"),
            )
        )
    # Live File section already shows Modified when the path exists; for a
    # missing path (and for Created, which File never shows) use the cache.
    if missing and record.file_modified_at:
        app_rows.append(
            (
                "recent.prop_file_modified",
                translate("recent.prop_file_modified", "Date modified"),
                format_absolute_timestamp(record.file_modified_at),
            )
        )
    created = record.file_created_at
    if not created and not missing:
        _modified_live, created = _snapshot_file_times(record.path)
    if created:
        app_rows.append(
            (
                "recent.prop_file_created",
                translate("recent.prop_file_created", "Date created"),
                format_absolute_timestamp(created),
            )
        )
    pinned = format_absolute_timestamp(record.pinned_at or record.opened_at)
    app_rows.append(
        (
            "recent.prop_pinned",
            translate("recent.prop_pinned", "Added to Recent"),
            pinned,
        )
    )
    app_rows.append(
        (
            "recent.prop_opened",
            translate("recent.prop_opened", "Last opened"),
            format_absolute_timestamp(record.opened_at),
        )
    )
    sessions = format_session_types(record.session_types, translate)
    if sessions:
        app_rows.append(
            (
                "recent.prop_sessions",
                translate("recent.prop_sessions", "Sessions"),
                sessions,
            )
        )

    def _dialog_tr(key, language=None, default=None, *args, **kwargs):
        key_text = str(key or "")
        if key_text.startswith("recent."):
            return translate(key_text, default if default is not None else key_text)
        return app_tr(key, language, default, *args, **kwargs)

    open_image_properties_dialog(
        parent=parent,
        path=record.path,
        display_name=record.display_name,
        image=None,
        app_rows=tuple(app_rows),
        language=lang,
        tr_func=_dialog_tr,
        probe_image=False,
    )
