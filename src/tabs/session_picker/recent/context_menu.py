"""Context menu actions for a recent project card."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QCursor, QDesktopServices
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator

from plugins.image_properties.plugin import open_image_properties_dialog
from resources.translations import get_current_language
from resources.translations import tr as app_tr
from services.io.recent_projects import RecentProjectRecord, _snapshot_file_times
from tabs.session_picker.recent.cards import format_session_types
from tabs.session_picker.recent.relative_time import format_absolute_timestamp
from ui.context_menu.manager import open_context_menu_entries


def open_recent_project_menu(
    *,
    source_widget,
    record: RecentProjectRecord,
    tr: Callable[..., str],
    on_open: Callable[[RecentProjectRecord], None],
    on_remove: Callable[[RecentProjectRecord], None],
) -> None:
    missing = not Path(record.path).is_file()
    entries = [
        ContextMenuAction(
            "recent.open",
            tr("recent.action_open", "Open"),
            enabled=not missing,
        ),
        ContextMenuAction(
            "recent.properties",
            tr("recent.action_properties", "Properties"),
        ),
        ContextMenuAction(
            "recent.remove",
            tr("recent.action_remove", "Remove from list"),
        ),
        ContextMenuSeparator(),
        ContextMenuAction(
            "recent.reveal",
            tr("recent.action_reveal", "Show in folder"),
            enabled=Path(record.path).parent.is_dir(),
        ),
    ]

    def on_triggered(action_id: str, _data: object) -> None:
        if action_id == "recent.open":
            on_open(record)
        elif action_id == "recent.properties":
            open_recent_project_properties(record, tr=tr, parent=source_widget)
        elif action_id == "recent.remove":
            on_remove(record)
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


def open_recent_project_properties(
    record: RecentProjectRecord,
    *,
    tr: Callable[..., str],
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
                tr("recent.prop_status", "Status"),
                tr("recent.missing", "File missing"),
            )
        )
    # Live File section already shows Modified when the path exists; for a
    # missing path (and for Created, which File never shows) use the cache.
    if missing and record.file_modified_at:
        app_rows.append(
            (
                "recent.prop_file_modified",
                tr("recent.prop_file_modified", "Date modified"),
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
                tr("recent.prop_file_created", "Date created"),
                format_absolute_timestamp(created),
            )
        )
    pinned = format_absolute_timestamp(record.pinned_at or record.opened_at)
    app_rows.append(
        (
            "recent.prop_pinned",
            tr("recent.prop_pinned", "Added to Recent"),
            pinned,
        )
    )
    app_rows.append(
        (
            "recent.prop_opened",
            tr("recent.prop_opened", "Last opened"),
            format_absolute_timestamp(record.opened_at),
        )
    )
    sessions = format_session_types(record.session_types, tr)
    if sessions:
        app_rows.append(
            (
                "recent.prop_sessions",
                tr("recent.prop_sessions", "Sessions"),
                sessions,
            )
        )

    def _dialog_tr(key, language=None, default=None, *args, **kwargs):
        key_text = str(key or "")
        if key_text.startswith("recent."):
            return tr(key_text, default if default is not None else key_text)
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
