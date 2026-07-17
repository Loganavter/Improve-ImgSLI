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
import logging
from pathlib import Path
from typing import Any

from core.store import INITIAL_WORKSPACE_SESSION_TYPE

logger = logging.getLogger("ImproveImgSLI")

PROJECT_FORMAT = "imgsli-project"
PROJECT_VERSION = 1
_KNOWN_PROJECT_KEYS = frozenset(
    {"format", "version", "active_session_index", "sessions"}
)


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


def _validate_project_container(project: dict[str, Any]) -> None:
    if project.get("format") != PROJECT_FORMAT:
        raise ValueError(f"Not a {PROJECT_FORMAT!r} project file")

    version = project.get("version")
    if not isinstance(version, int):
        raise ValueError("Project file is missing a valid version field")
    if version > PROJECT_VERSION:
        raise ValueError(
            f"Project file version {version} is newer than supported "
            f"version {PROJECT_VERSION}"
        )

    unknown = set(project.keys()) - _KNOWN_PROJECT_KEYS
    if unknown:
        logger.warning(
            "Project file contains unknown top-level fields (ignored): %s",
            sorted(unknown),
        )


def clear_workspace_sessions(
    workspace_actions: Any,
    store: Any,
    *,
    keep_one_picker: bool = True,
) -> str | None:
    """Close every workspace session except one placeholder picker session.

    Returns the session id that was kept (or created). Used before a
    programmatic "replace workspace" project load.
    """
    sessions = list(store.list_workspace_sessions())
    keeper_id: str | None = None
    if keep_one_picker:
        for session in sessions:
            if session.session_type == INITIAL_WORKSPACE_SESSION_TYPE:
                keeper_id = session.id
                break
        if keeper_id is None:
            picker = workspace_actions.create_workspace_session(
                INITIAL_WORKSPACE_SESSION_TYPE,
                activate=False,
            )
            keeper_id = picker.id
            sessions = list(store.list_workspace_sessions())

    for session in list(store.list_workspace_sessions()):
        if keeper_id is not None and session.id == keeper_id:
            continue
        if len(store.list_workspace_sessions()) <= 1:
            break
        workspace_actions.close_workspace_session(session.id)

    if keeper_id is not None:
        workspace_actions.switch_workspace_session(keeper_id)
    active = store.get_active_workspace_session()
    return active.id if active is not None else keeper_id


def load_project_data(
    project: dict[str, Any],
    workspace_actions: Any,
    store: Any,
    tab_registry: Any,
    *,
    replace_workspace: bool = False,
) -> list[Any]:
    """Create a fresh workspace session per persisted entry and restore each
    via its owning tab's `deserialize_session`.

    Sessions are created through `workspace_actions` (the same
    `WorkspaceSessionActions` funnel used everywhere else — see
    `docs/dev/TODO.md`'s "Wire on_session_created / on_session_closed") so
    session-blueprint defaults and lifecycle events fire normally;
    `deserialize_session` then overwrites those defaults with the persisted
    data. When ``replace_workspace`` is True, existing sessions are cleared
    first (keeping one ``session_picker`` placeholder).

    Returns the created `WorkspaceSession` objects, in file order.
    """
    _validate_project_container(project)

    if replace_workspace:
        clear_workspace_sessions(workspace_actions, store, keep_one_picker=True)

    created_ids: list[str] = []
    for entry in project.get("sessions", []):
        session_type = entry["session_type"]
        session = workspace_actions.create_workspace_session(
            session_type, activate=False, title=entry.get("title")
        )
        tab_registry.deserialize_session(session_type, session.id, entry.get("data") or {})
        tab_registry.rehydrate_session(session_type, session.id)
        created_ids.append(session.id)

    active_index = project.get("active_session_index")
    if active_index is not None and 0 <= active_index < len(created_ids):
        workspace_actions.switch_workspace_session(created_ids[active_index])

    return [store.get_workspace_session(sid) for sid in created_ids]


def save_project_file(path: str | Path, store: Any, tab_registry: Any) -> None:
    data = build_project_data(store, tab_registry)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project_file(
    path: str | Path,
    workspace_actions: Any,
    store: Any,
    tab_registry: Any,
    *,
    replace_workspace: bool = False,
) -> list[Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_project_data(
        data,
        workspace_actions,
        store,
        tab_registry,
        replace_workspace=replace_workspace,
    )
