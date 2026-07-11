"""Project file I/O — snapshot/restore the whole workspace to/from a JSON file.

Delegates all tab-specific state to each tab's `TabContract.serialize_session`
/ `deserialize_session` hooks via `TabRegistry`; this module only knows about
`WorkspaceSession` bookkeeping (which sessions exist, which is active) and the
on-disk container format. Sessions whose tab does not implement the hooks
(`serialize_session` returns None) are silently omitted from the save — they
are not yet restorable from a project file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_FORMAT = "imgsli-project"
PROJECT_VERSION = 1


def build_project_data(store: Any, tab_registry: Any) -> dict[str, Any]:
    """Snapshot every workspace session into a JSON-serializable dict."""
    active = store.get_active_workspace_session()
    active_id = active.id if active is not None else None

    sessions_data: list[dict[str, Any]] = []
    active_index: int | None = None
    for session in store.list_workspace_sessions():
        data = tab_registry.serialize_session(session.session_type, session.id)
        if data is None:
            continue
        if session.id == active_id:
            active_index = len(sessions_data)
        sessions_data.append(
            {
                "session_type": session.session_type,
                "title": session.title,
                "data": data,
            }
        )

    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "active_session_index": active_index,
        "sessions": sessions_data,
    }


def load_project_data(
    project: dict[str, Any], workspace_actions: Any, store: Any, tab_registry: Any
) -> list[Any]:
    """Create a fresh workspace session per persisted entry and restore each
    via its owning tab's `deserialize_session`.

    Sessions are created through `workspace_actions` (the same
    `WorkspaceSessionActions` funnel used everywhere else — see
    `docs/dev/TODO.md`'s "Wire on_session_created / on_session_closed") so
    session-blueprint defaults and lifecycle events fire normally;
    `deserialize_session` then overwrites those defaults with the persisted
    data. Does not close or replace any pre-existing sessions — callers that
    want a clean "Open Project" should close existing sessions first.

    Returns the created `WorkspaceSession` objects, in file order.
    """
    if project.get("format") != PROJECT_FORMAT:
        raise ValueError(f"Not a {PROJECT_FORMAT!r} project file")

    created_ids: list[str] = []
    for entry in project.get("sessions", []):
        session_type = entry["session_type"]
        session = workspace_actions.create_workspace_session(
            session_type, activate=False, title=entry.get("title")
        )
        tab_registry.deserialize_session(session_type, session.id, entry.get("data") or {})
        created_ids.append(session.id)

    active_index = project.get("active_session_index")
    if active_index is not None and 0 <= active_index < len(created_ids):
        workspace_actions.switch_workspace_session(created_ids[active_index])

    return [store.get_workspace_session(sid) for sid in created_ids]


def save_project_file(path: str | Path, store: Any, tab_registry: Any) -> None:
    data = build_project_data(store, tab_registry)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project_file(
    path: str | Path, workspace_actions: Any, store: Any, tab_registry: Any
) -> list[Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_project_data(data, workspace_actions, store, tab_registry)
