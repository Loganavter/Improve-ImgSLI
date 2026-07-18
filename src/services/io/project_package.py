"""ZIP package helpers for portable ``.imgsli`` project files.

Layout::

    project.json
    preview.jpg          (optional scene thumbnail)
    media/<asset_id>/<original_basename>

Images are byte-copied (not re-encoded). ``asset_id`` is the first 16 hex
chars of the file SHA-256. Session path fields are rewritten to
``media/<asset_id>/<name>`` on save and to absolute cache paths on load.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger("ImproveImgSLI")

PROJECT_JSON_NAME = "project.json"
MEDIA_PREFIX = "media/"
ASSET_ID_LEN = 16

# Path-bearing keys inside tab session blobs (IC + MC).
_LIST_PATH_KEYS = ("image_list1", "image_list2")
_SCALAR_PATH_KEYS = ("image1_path", "image2_path")
_SLOT_LIST_KEY = "slots"


def is_zip_project(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    return zipfile.is_zipfile(path)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def asset_id_from_digest(digest: str) -> str:
    return digest[:ASSET_ID_LEN]


def media_member_path(asset_id: str, basename: str) -> str:
    safe_name = Path(basename).name or "asset"
    return f"{MEDIA_PREFIX}{asset_id}/{safe_name}"


def project_cache_dir(project_path: Path) -> Path:
    """Stable per-project extract cache under the Qt/app cache location."""
    resolved = project_path.resolve()
    try:
        mtime_ns = resolved.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    key_src = f"{resolved}:{mtime_ns}".encode("utf-8")
    key = hashlib.sha256(key_src).hexdigest()[:24]
    root = _cache_root()
    return root / "projects" / key


def _cache_root() -> Path:
    override = os.environ.get("IMGSLI_PROJECT_CACHE")
    if override:
        return Path(override)
    try:
        from PySide6.QtCore import QStandardPaths

        loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if loc:
            root = Path(loc)
            # Bare ``~/.cache`` (no org/app name) still needs an app subdirectory.
            if root.name.lower() not in {"improveimgsli", "pytest-qt-qapp"}:
                root = root / "ImproveImgSLI"
            return root
    except Exception:
        pass
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "ImproveImgSLI"
    return Path.home() / ".cache" / "ImproveImgSLI"


def iter_session_media_paths(project_data: dict[str, Any]) -> list[str]:
    """Collect absolute or package-relative path strings from session blobs."""
    found: list[str] = []
    for entry in project_data.get("sessions") or []:
        data = entry.get("data") or {}
        for key in _LIST_PATH_KEYS:
            for item in data.get(key) or []:
                if isinstance(item, dict):
                    path = item.get("path")
                    if path:
                        found.append(str(path))
        for key in _SCALAR_PATH_KEYS:
            path = data.get(key)
            if path:
                found.append(str(path))
        for slot in data.get(_SLOT_LIST_KEY) or []:
            if isinstance(slot, dict):
                path = slot.get("path")
                if path:
                    found.append(str(path))
    return found


def rewrite_session_paths(
    project_data: dict[str, Any],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Return a deep-copied project dict with path fields remapped.

    ``mapping`` keys are the current path strings; values are replacements.
    Paths absent from ``mapping`` are left unchanged.
    """

    def _map(path: str | None) -> str | None:
        if not path:
            return path
        return mapping.get(str(path), str(path))

    sessions_out: list[dict[str, Any]] = []
    for entry in project_data.get("sessions") or []:
        data = dict(entry.get("data") or {})
        for key in _LIST_PATH_KEYS:
            items = data.get(key)
            if not items:
                continue
            data[key] = [
                {**item, "path": _map(item.get("path")) or ""}
                if isinstance(item, dict)
                else item
                for item in items
            ]
        for key in _SCALAR_PATH_KEYS:
            if key in data:
                data[key] = _map(data.get(key))
        slots = data.get(_SLOT_LIST_KEY)
        if slots:
            data[_SLOT_LIST_KEY] = [
                {**slot, "path": _map(slot.get("path"))}
                if isinstance(slot, dict)
                else slot
                for slot in slots
            ]
        sessions_out.append(
            {
                "session_type": entry.get("session_type"),
                "title": entry.get("title"),
                "data": data,
            }
        )

    out = dict(project_data)
    out["sessions"] = sessions_out
    return out


def embed_media(
    source_paths: Iterable[str],
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    """Hash and stage unique existing files for ZIP embedding.

    Returns ``(abs_path -> media/… member, media catalog, missing abs paths)``.
    """
    path_to_member: dict[str, str] = {}
    catalog: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    # digest -> member path (dedup)
    digest_members: dict[str, str] = {}

    unique: list[Path] = []
    seen: set[str] = set()
    for raw in source_paths:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        unique.append(Path(raw))

    total = len(unique)
    for index, path in enumerate(unique):
        if progress is not None:
            progress(index, total, str(path))
        if not path.is_file():
            missing.append(str(path))
            continue
        try:
            digest = sha256_file(path)
        except OSError:
            logger.exception("Failed to hash project media %s", path)
            missing.append(str(path))
            continue
        if digest in digest_members:
            path_to_member[str(path)] = digest_members[digest]
            continue
        aid = asset_id_from_digest(digest)
        member = media_member_path(aid, path.name)
        digest_members[digest] = member
        path_to_member[str(path)] = member
        catalog[aid] = {
            "name": path.name,
            "sha256": digest,
            "bytes": path.stat().st_size,
            "member": member,
        }
    if progress is not None and total:
        progress(total, total, "")
    return path_to_member, catalog, missing


def write_project_zip(
    path: str | Path,
    project_data: dict[str, Any],
    path_to_member: dict[str, str],
    *,
    progress: Callable[[int, int, str], None] | None = None,
    preview_jpeg: bytes | None = None,
) -> None:
    """Atomically write a ZIP project containing ``project.json`` + media.

    Optional ``preview_jpeg`` is stored as top-level ``preview.jpg`` (scene thumb).
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Reverse map: member -> first absolute source
    member_to_source: dict[str, Path] = {}
    for abs_path, member in path_to_member.items():
        member_to_source.setdefault(member, Path(abs_path))

    members = sorted(member_to_source.keys())
    has_preview = bool(preview_jpeg)
    total = len(members) + 1 + (1 if has_preview else 0)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.stem}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zf:
            payload = json.dumps(project_data, indent=2, ensure_ascii=False)
            zf.writestr(PROJECT_JSON_NAME, payload.encode("utf-8"))
            done = 1
            if progress is not None:
                progress(done, total, PROJECT_JSON_NAME)
            if has_preview:
                from services.io.project_preview import PREVIEW_MEMBER

                zf.writestr(PREVIEW_MEMBER, preview_jpeg)
                done += 1
                if progress is not None:
                    progress(done, total, PREVIEW_MEMBER)
            for index, member in enumerate(members, start=done + 1):
                source = member_to_source[member]
                if progress is not None:
                    progress(index - 1, total, str(source))
                zf.write(source, arcname=member)
            if progress is not None:
                progress(total, total, "")
        os.replace(tmp_path, dest)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def read_project_json_from_zip(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path, "r") as zf:
        with zf.open(PROJECT_JSON_NAME) as fh:
            return json.loads(fh.read().decode("utf-8"))


def extract_media(
    path: str | Path,
    cache_dir: Path,
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    """Extract ``media/`` members to ``cache_dir``.

    Returns ``{package_relative_member: absolute_cache_path}``.
    Reuses existing files when present and non-empty.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    with zipfile.ZipFile(path, "r") as zf:
        members = [
            name
            for name in zf.namelist()
            if name.startswith(MEDIA_PREFIX) and not name.endswith("/")
        ]
        total = len(members)
        for index, member in enumerate(members):
            if progress is not None:
                progress(index, total, member)
            # Guard against zip-slip
            target = (cache_dir / member).resolve()
            if not str(target).startswith(str(cache_dir.resolve())):
                raise ValueError(f"Unsafe zip member path: {member}")
            if target.is_file() and target.stat().st_size > 0:
                mapping[member] = str(target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            mapping[member] = str(target)
        if progress is not None and total:
            progress(total, total, "")
    return mapping
