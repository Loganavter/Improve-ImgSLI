"""Records/prefs refresh and rebuild for ``RecentProjectsPanel`` -- split out
to keep that class down to composition/wiring, mirroring the ``use_cases``
split applied elsewhere (see docs/dev/CODE_PATTERNS.md). Every function here
takes the panel as its first argument and reads/writes its instance state
(``_records``, ``_view_mode``, ``_sort_mode``, ``_sort_order``,
``_selected_paths``, ``_layout_ready``) directly.

Cross-calls go through ``panel.<method>()`` (not the sibling module function
directly) even within this module -- tests monkeypatch instance methods
like ``panel._rebuild_items`` directly (see
``src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py``), which only takes effect
if callers look the method up on the instance each time.

The ``services.io.recent_projects`` reads/writes below go through the
``tabs.session_picker.recent.panel`` module (imported lazily inside each
function to dodge the circular import -- ``panel.py`` imports this module),
not straight from ``services.io.recent_projects``, because
``src/tabs/session_picker/tests/runtime/test_recent_projects_panel.py``/``test_recent_selection.py``
monkeypatch e.g. ``"tabs.session_picker.recent.panel.list_recent_projects"``
-- a direct import here would bind before the patch and never see it.
"""

from __future__ import annotations

import os


def _disk_fingerprint(path: str) -> tuple[bool, int | None]:
    """On-disk presence + mtime for a recent record.

    Fail-open (``(False, None)``) when the path cannot be stated — an
    unstatable file counts as changed, never as silently fresh.
    """
    try:
        return (True, int(os.stat(path).st_mtime_ns))
    except OSError:
        try:
            # Deleted externally (or never existed): presence is the signal.
            return (os.path.exists(path), None)
        except Exception:
            return (False, None)


def _record_signature(records) -> list[tuple]:
    """Stored-field identity per record (prefs-level change detection)."""
    return [
        (r.path, r.opened_at, r.display_name, r.session_types)
        for r in records
    ]


def _live_state(records) -> list[tuple]:
    """Live on-disk state per record — compared against the panel's last-seen
    snapshot, not against the fresh list.

    Comparing old-vs-fresh record *fields* can never catch an external delete:
    both sides come from the same store file, so both still claim the project
    exists. Only a snapshot of what the disk looked like at the last refresh
    makes deletes/mtime edits visible.
    """
    return [(r.path, *_disk_fingerprint(r.path)) for r in records]


def refresh(panel) -> None:
    from tabs.session_picker.recent import panel as _panel_mod

    panel._view_mode = _panel_mod.get_recent_view_mode()
    panel._sort_mode = _panel_mod.get_recent_sort_mode()
    panel._sort_order = _panel_mod.get_recent_sort_order()
    records = _panel_mod.list_recent_projects(drop_missing=False)
    panel._records = _panel_mod.sort_recent_projects(
        records,
        sort_by=panel._sort_mode,
        sort_order=panel._sort_order,
    )
    alive = {r.path for r in panel._records}
    panel._selected_paths &= alive
    panel._disk_snapshot = _live_state(panel._records)
    panel._rebuild_items()
    panel._sync_header_controls()
    panel._sync_opaque_fills()
    panel._layout_ready = True
    panel._items.apply_selection()


def soft_refresh(panel) -> None:
    """Update shelf contents only when records or view prefs changed."""
    from tabs.session_picker.recent import panel as _panel_mod

    view_mode = _panel_mod.get_recent_view_mode()
    sort_mode = _panel_mod.get_recent_sort_mode()
    sort_order = _panel_mod.get_recent_sort_order()
    records = _panel_mod.sort_recent_projects(
        _panel_mod.list_recent_projects(drop_missing=False),
        sort_by=sort_mode,
        sort_order=sort_order,
    )
    same_prefs = (
        view_mode == panel._view_mode
        and sort_mode == panel._sort_mode
        and sort_order == panel._sort_order
    )
    same_records = _record_signature(panel._records) == _record_signature(records)
    live_now = _live_state(records)
    prev_live = getattr(panel, "_disk_snapshot", None)
    disk_changed = prev_live is not None and prev_live != live_now
    if same_prefs and same_records and not disk_changed:
        panel._sync_header_controls()
        panel._disk_snapshot = live_now
        return
    panel._view_mode = view_mode
    panel._sort_mode = sort_mode
    panel._sort_order = sort_order
    panel._records = records
    panel._disk_snapshot = live_now
    panel._selected_paths &= {r.path for r in records}
    panel._rebuild_items()
    panel._sync_header_controls()
    panel._sync_opaque_fills()
    panel._items.apply_selection()


def rebuild_items(panel) -> None:
    has_items = bool(panel._records)
    if panel._empty_zone is not None:
        panel._empty_zone.setVisible(not has_items)
    panel._header.set_controls_visible(has_items)
    panel._items.rebuild(
        records=panel._records,
        view_mode=panel._view_mode,
        updates_owner=panel,
    )
    panel._sync_opaque_fills()


def pin_dropped_paths(panel, paths: list[str]) -> None:
    from tabs.session_picker.recent import panel as _panel_mod

    toast = getattr(panel.window(), "toast_manager", None)
    for path in paths:
        try:
            result = _panel_mod.record_recent_project(path)
            _panel_mod.notify_recent_cap_eviction(
                result.evicted,
                toast_manager=toast,
                tr=panel._tr,
            )
        except Exception:
            continue
    panel.refresh()
