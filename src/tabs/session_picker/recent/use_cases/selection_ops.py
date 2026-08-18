"""Selection, activation, and removal for ``RecentProjectsPanel`` -- split
out to keep that class down to composition/wiring, mirroring the
``use_cases`` split applied elsewhere (see docs/dev/CODE_PATTERNS.md). Every
function here takes the panel as its first argument and reads/writes its
``_selected_paths`` instance state directly.

Cross-calls go through ``panel.<method>()`` (not the sibling module function
directly) even within this module, matching ``use_cases/refresh.py``'s
rationale -- keeps behavior identical if a caller monkeypatches an instance
method. ``remove_recent_project`` is likewise re-read from the ``panel``
module (imported lazily to dodge the circular import) rather than imported
straight from ``services.io.recent_projects``, since
``src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py`` monkeypatches
``"tabs.session_picker.recent.panel.remove_recent_project"``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from services.io.recent_projects import RecentProjectRecord


def on_marquee_preview(panel, paths: set[str], additive: bool) -> None:
    from ui.widgets.shelf.selection import preview_selection

    # Non-additive: band-only preview (clears prior highlight while dragging).
    base = panel._selected_paths if additive else set()
    panel._items.apply_selection(
        preview_selection(base, paths, additive=additive)
    )


def on_marquee_commit(panel, paths: set[str], additive: bool) -> None:
    if additive:
        panel._selected_paths |= paths
    else:
        panel._selected_paths = set(paths)
    panel._items.apply_selection()
    panel.setFocus(Qt.FocusReason.MouseFocusReason)


def clear_selection(panel) -> None:
    if not panel._selected_paths:
        return
    panel._selected_paths.clear()
    panel._items.apply_selection()


def on_card_activate(
    panel,
    record: RecentProjectRecord,
    missing: bool,
    modifiers=Qt.KeyboardModifier.NoModifier,
) -> None:
    from ui.widgets.shelf.selection import ctrl_held

    if ctrl_held(modifiers):
        path = record.path
        if path in panel._selected_paths:
            panel._selected_paths.discard(path)
        else:
            panel._selected_paths.add(path)
        panel._items.apply_selection()
        panel.setFocus(Qt.FocusReason.MouseFocusReason)
        return
    panel._clear_selection()
    panel._activate(record, missing)


def activate(panel, record: RecentProjectRecord, missing: bool) -> None:
    # Re-check on disk: cards can stay "alive" after the file was deleted.
    exists = Path(record.path).is_file()
    if missing or not exists:
        # Keep the pinned entry. Removal is only via the context menu.
        # If the card still looked "alive", rebuild into the missing state.
        if not missing:
            panel.refresh()
        return
    if panel._on_open is not None:
        panel._on_open(record.path)


def show_context_menu(panel, record: RecentProjectRecord) -> None:
    from tabs.session_picker.recent.context_menu import open_recent_project_menu

    selected = set(panel._selected_paths)
    if record.path not in selected:
        # Right-click outside the current selection → single-item menu.
        selected = set()
    open_recent_project_menu(
        source_widget=panel.window() or panel,
        record=record,
        tr=panel._tr,
        on_open=lambda r: panel._activate(r, missing=False),
        on_remove=panel._remove_record,
        selected_paths=selected,
        on_remove_selected=panel._remove_selected_paths,
    )


def remove_record(panel, record: RecentProjectRecord) -> None:
    from tabs.session_picker.recent import panel as _panel_mod

    _panel_mod.remove_recent_project(record.path)
    panel._selected_paths.discard(record.path)
    panel.refresh()


def remove_selected_paths(panel) -> None:
    from tabs.session_picker.recent import panel as _panel_mod

    paths = list(panel._selected_paths)
    if not paths:
        return
    for path in paths:
        _panel_mod.remove_recent_project(path)
    panel._selected_paths.clear()
    panel.refresh()
