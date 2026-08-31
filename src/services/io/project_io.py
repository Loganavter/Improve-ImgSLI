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
    embed_pixel_cache_sources,
    extract_media,
    extract_pixel_cache,
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
PROJECT_VERSION = 3
_KNOWN_PROJECT_KEYS = frozenset(
    {"format", "version", "active_session_index", "sessions", "media", "pixel_cache"}
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
        "pixel_cache": {},
    }


def collect_pixel_cache_sources(store: Any, tab_registry: Any) -> dict[str, tuple[Any, int, int]]:
    """``{abs source path: (open fd, width, height)}`` for every live, open
    ``TiledPixelStore`` across all workspace sessions.

    Must run on the UI thread, right after :func:`build_project_data` — opens
    each store's spill file fd immediately so a later swap/close on the UI
    thread can't race a worker-thread copy (unlink never invalidates an
    already-open fd on Linux, so the fd stays a consistent snapshot).
    """
    sources: dict[str, tuple[Any, int, int]] = {}
    opened_paths: set[str] = set()
    for session in store.list_workspace_sessions():
        session_sources = tab_registry.collect_pixel_cache_sources(
            session.session_type, session.id
        )
        for path, tiled_store in (session_sources or {}).items():
            store_path = getattr(tiled_store, "path", None)
            if not path or not store_path or store_path in opened_paths:
                continue
            try:
                fd = open(store_path, "rb")
            except OSError:
                logger.exception("Failed to open pixel cache source %s", store_path)
                continue
            opened_paths.add(store_path)
            width, height = tiled_store.width, tiled_store.height
            sources[path] = (fd, width, height)
    return sources


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
    include_pixel_cache: bool = False,
) -> list[str]:
    """Save a portable ZIP project (v2) with embedded media copies.

    Snapshot is taken immediately from ``store`` (must be on the UI thread).
    Hashing/copying media and writing the ZIP may be slow — prefer
    :func:`package_project_data` on a worker after calling
    :func:`build_project_data` on the UI thread.

    ``include_pixel_cache`` additionally embeds each live session's decoded
    RGBA8 spill buffer so a future reopen can skip re-decoding; only this
    module's synchronous convenience path is affected — the real UI save flow
    (``ui.main_window.project_io``) collects pixel-cache sources separately.

    Returns a list of source paths that could not be embedded (missing/unreadable).
    """
    data = build_project_data(store, tab_registry)
    pixel_cache_sources = (
        collect_pixel_cache_sources(store, tab_registry) if include_pixel_cache else None
    )
    return package_project_data(
        data, path, progress=progress, pixel_cache_sources=pixel_cache_sources
    )


def package_project_data(
    project_data: dict[str, Any],
    path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    preview_png: bytes | None = None,
    preview_jpeg: bytes | None = None,
    pixel_cache_sources: dict[str, tuple[Any, int, int]] | None = None,
) -> list[str]:
    """Embed media and write a ZIP from an already-built project snapshot.

    Safe to call off the UI thread: does not touch Qt widgets or the Store.
    Optional ``preview_png`` is written as top-level ``preview.png`` (canvas
    scene grab). ``preview_jpeg`` is a deprecated alias. Optional
    ``pixel_cache_sources`` is ``{abs source path: (open fd, width, height)}``
    from :func:`collect_pixel_cache_sources` (UI thread) — each fd is closed
    once written or on failure.
    """
    source_paths = iter_session_media_paths(project_data)
    path_to_member, catalog, missing = embed_media(source_paths, progress=progress)
    rewritten = rewrite_session_paths(project_data, path_to_member)
    rewritten["format"] = PROJECT_FORMAT
    rewritten["version"] = PROJECT_VERSION
    rewritten["media"] = catalog
    cache_members: dict[str, Any] = {}
    if pixel_cache_sources:
        cache_members, cache_catalog = embed_pixel_cache_sources(
            pixel_cache_sources, path_to_member
        )
        rewritten["pixel_cache"] = cache_catalog
    else:
        rewritten["pixel_cache"] = {}
    write_project_zip(
        path,
        rewritten,
        path_to_member,
        progress=progress,
        preview_png=preview_png if preview_png is not None else preview_jpeg,
        cache_members=cache_members,
    )
    if missing:
        logger.warning(
            "Project save omitted %d missing media path(s): %s",
            len(missing),
            missing[:8],
        )
    return missing


def _is_unc_path(path_str: str) -> bool:
    r"""True for Windows UNC (\\host\share or //host/share) that would trigger SMB."""
    return path_str.startswith("\\\\") or path_str.startswith("//")


def _collect_legacy_path_warnings(data: dict[str, Any]) -> list[str]:
    """Warn about absolute/UNC paths in legacy v1 projects (W3.3)."""
    warns: list[str] = []
    for p in iter_session_media_paths(data):
        s = str(p)
        if _is_unc_path(s):
            warns.append(f"UNC path {s!r} in legacy project — may trigger SMB credential exchange")
        elif Path(s).is_absolute():
            warns.append(f"Absolute path {s!r} in legacy project")
    return warns


def _register_pixel_cache(
    data: dict[str, Any],
    project_path: Path,
    cache_dir: Path,
    member_to_abs: dict[str, str],
    *,
    progress: ProgressCallback | None = None,
    embedded_cache=None,
) -> None:
    """Extract embedded ``cache/`` buffers (if any) and register them so the
    ``TiledPixelStore.from_path`` call sites can skip re-decoding.

    W3.1: clamp dims vs MAX_SUPPORTED_IMAGE_DIMENSION and verify
    ``st_size >= w*h*4`` before memmap to avoid SIGBUS on crafted projects.
    ``embedded_cache`` — DI для embedded tier (PipelineCache или registry
    объект с ``register``). Если ``None`` — используется host-owned
    ``shared.image_processing.embedded_pixel_cache`` (без импорта ``tabs``).
    """
    pixel_cache = data.get("pixel_cache")
    if not pixel_cache:
        return
    media_catalog = data.get("media") or {}
    try:
        asset_to_extracted = extract_pixel_cache(project_path, cache_dir, progress=progress)
    except Exception:
        logger.exception("Failed to extract embedded pixel cache from %s", project_path)
        return

    from core.constants import AppConstants

    # DI: prefer injected cache (PipelineCache instance / registry), fallback to host module
    _injected_register = None
    if embedded_cache is not None:
        try:
            if hasattr(embedded_cache, "register"):
                _injected_register = embedded_cache.register  # type: ignore
            elif hasattr(embedded_cache, "register_embedded_cache"):
                _injected_register = embedded_cache.register_embedded_cache  # type: ignore
        except Exception:
            _injected_register = None
    if _injected_register is None:
        from shared.image_processing import embedded_pixel_cache as _emb

        _injected_register = _emb.register

    for asset_id, entry in pixel_cache.items():
        extracted_path = asset_to_extracted.get(asset_id)
        media_entry = media_catalog.get(asset_id)
        if not extracted_path or not media_entry:
            continue
        member = media_entry.get("member")
        abs_media_path = member_to_abs.get(member) if member else None
        raw_w, raw_h = entry.get("width"), entry.get("height")
        if not abs_media_path or raw_w is None or raw_h is None:
            continue
        try:
            width = int(raw_w)
            height = int(raw_h)
        except (TypeError, ValueError):
            logger.warning("Skipping pixel_cache %s: non-int dims %r x %r", asset_id, raw_w, raw_h)
            continue
        max_dim = int(AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION)
        if width <= 0 or height <= 0 or width > max_dim or height > max_dim:
            logger.warning(
                "Skipping pixel_cache %s: dims %dx%d out of bounds (max %d)",
                asset_id, width, height, max_dim,
            )
            continue
        try:
            st_size = Path(extracted_path).stat().st_size
        except OSError as exc:
            logger.warning("Skipping pixel_cache %s: cannot stat %s: %s", asset_id, extracted_path, exc)
            continue
        expected = width * height * 4
        if st_size < expected:
            logger.warning(
                "Skipping pixel_cache %s: file too small (%d < %d = %dx%dx4)",
                asset_id, st_size, expected, width, height,
            )
            continue
        _injected_register(abs_media_path, extracted_path, width, height)


def prepare_project_file_for_load(
    path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    embedded_cache=None,
) -> tuple[dict[str, Any], list[str]]:
    """Read/extract a project file into a loadable dict (worker-safe).

    Returns ``(project_data, warnings)``. For ZIP packages, media is extracted
    to the project cache and path fields are rewritten to absolute cache paths.
    Does not mutate the workspace — call :func:`load_project_data` on the UI
    thread afterward. ``embedded_cache`` — DI для embedded tier (см. ``_register_pixel_cache``).
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
        _register_pixel_cache(
            data, project_path, cache_dir, member_to_abs, progress=progress, embedded_cache=embedded_cache
        )
        return data, warnings

    data = json.loads(project_path.read_text(encoding="utf-8"))
    _validate_project_container(data)
    legacy_warns = _collect_legacy_path_warnings(data)
    for w in legacy_warns:
        logger.warning(w)
    warnings.extend(legacy_warns)
    return data, warnings


def load_project_file(
    path: str | Path,
    workspace_actions: Any,
    store: Any,
    tab_registry: Any,
    *,
    replace_workspace: bool = True,
    progress: ProgressCallback | None = None,
    embedded_cache=None,
) -> list[Any]:
    """Load a project file (ZIP v2 or legacy plain JSON v1).

    Default ``replace_workspace=True`` so Open replaces the current workspace.
    ``embedded_cache`` forwarded to ``prepare_project_file_for_load`` (DI).
    """
    data, _warnings = prepare_project_file_for_load(path, progress=progress, embedded_cache=embedded_cache)
    return load_project_data(
        data,
        workspace_actions,
        store,
        tab_registry,
        replace_workspace=replace_workspace,
    )
