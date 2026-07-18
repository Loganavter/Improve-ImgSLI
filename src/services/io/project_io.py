"""Project file I/O — snapshot/restore the whole workspace to/from a package.

Delegates all tab-specific state to each tab's `TabContract.serialize_session`
/ `deserialize_session` hooks via `TabRegistry`; this module only knows about
`WorkspaceSession` bookkeeping (which sessions exist, which is active) and the
on-disk container format. Sessions whose tab does not implement the hooks
(`serialize_session` returns None) are silently omitted from the save — they
are not yet restorable from a project file.

Version 2 portable packages are ZIP files containing ``project.json`` plus
byte-copied media under ``media/<asset_id>/``. Plain JSON v1 files remain
loadable (path references only, no embedded media).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from services.io.project_package import (
    embed_media,
    extract_media,
    is_zip_project,
    iter_session_media_paths,
    project_cache_dir,
    read_project_json_from_zip,
    rewrite_session_paths,
    write_project_zip,
)

logger = logging.getLogger("ImproveImgSLI")

PROJECT_FORMAT = "imgsli"
# Legacy format id from early portable builds / plain-JSON v1.
_LEGACY_PROJECT_FORMATS = frozenset({PROJECT_FORMAT, "imgsli-project"})
PROJECT_VERSION = 2
_KNOWN_PROJECT_KEYS = frozenset(
    {"format", "version", "active_session_index", "sessions", "media"}
)
PROJECT_FILE_EXTENSION = ".imgsli"
_LEGACY_FILE_EXTENSIONS = (".imgsli", ".imgsli-project")

ProgressCallback = Callable[[int, int, str], None]


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
        "media": {},
    }


def _validate_project_container(project: dict[str, Any]) -> None:
    fmt = project.get("format")
    if fmt not in _LEGACY_PROJECT_FORMATS:
        raise ValueError(f"Not an Improve-ImgSLI project file (format={fmt!r})")

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
    `WorkspaceSessionActions` funnel used everywhere else) so
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


def save_project_file(
    path: str | Path,
    store: Any,
    tab_registry: Any,
    *,
    progress: ProgressCallback | None = None,
) -> list[str]:
    """Save a portable ZIP project (v2) with embedded media copies.

    Snapshot is taken immediately from ``store`` (must be on the UI thread).
    Hashing/copying media and writing the ZIP may be slow — prefer
    :func:`package_project_data` on a worker after calling
    :func:`build_project_data` on the UI thread.

    Returns a list of source paths that could not be embedded (missing/unreadable).
    """
    data = build_project_data(store, tab_registry)
    return package_project_data(data, path, progress=progress)


def package_project_data(
    project_data: dict[str, Any],
    path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    preview_jpeg: bytes | None = None,
) -> list[str]:
    """Embed media and write a ZIP from an already-built project snapshot.

    Safe to call off the UI thread: does not touch Qt widgets or the Store.
    Optional ``preview_jpeg`` is written as top-level ``preview.jpg``.
    """
    source_paths = iter_session_media_paths(project_data)
    path_to_member, catalog, missing = embed_media(source_paths, progress=progress)
    rewritten = rewrite_session_paths(project_data, path_to_member)
    rewritten["format"] = PROJECT_FORMAT
    rewritten["version"] = PROJECT_VERSION
    rewritten["media"] = catalog
    write_project_zip(
        path,
        rewritten,
        path_to_member,
        progress=progress,
        preview_jpeg=preview_jpeg,
    )
    if missing:
        logger.warning(
            "Project save omitted %d missing media path(s): %s",
            len(missing),
            missing[:8],
        )
    return missing


def prepare_project_file_for_load(
    path: str | Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Read/extract a project file into a loadable dict (worker-safe).

    Returns ``(project_data, warnings)``. For ZIP packages, media is extracted
    to the project cache and path fields are rewritten to absolute cache paths.
    Does not mutate the workspace — call :func:`load_project_data` on the UI
    thread afterward.
    """
    project_path = Path(path)
    if not project_path.is_file():
        raise FileNotFoundError(str(project_path))
    warnings: list[str] = []
    if is_zip_project(project_path):
        data = read_project_json_from_zip(project_path)
        _validate_project_container(data)
        cache_dir = project_cache_dir(project_path)
        member_to_abs = extract_media(project_path, cache_dir, progress=progress)
        # Drop references whose members failed to extract.
        missing_members = [
            p
            for p in iter_session_media_paths(data)
            if str(p).startswith("media/") and str(p) not in member_to_abs
        ]
        if missing_members:
            warnings.append(
                f"Missing {len(missing_members)} embedded media member(s) in project."
            )
        data = rewrite_session_paths(data, member_to_abs)
        return data, warnings

    data = json.loads(project_path.read_text(encoding="utf-8"))
    _validate_project_container(data)
    return data, warnings


def load_project_file(
    path: str | Path,
    workspace_actions: Any,
    store: Any,
    tab_registry: Any,
    *,
    replace_workspace: bool = True,
    progress: ProgressCallback | None = None,
) -> list[Any]:
    """Load a project file (ZIP v2 or legacy plain JSON v1).

    Default ``replace_workspace=True`` so Open replaces the current workspace.
    """
    data, _warnings = prepare_project_file_for_load(path, progress=progress)
    return load_project_data(
        data,
        workspace_actions,
        store,
        tab_registry,
        replace_workspace=replace_workspace,
    )
