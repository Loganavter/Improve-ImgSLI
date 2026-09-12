# Audit-Meta: pattern=state-machine reason="single ZIP package lifecycle — media/cache extraction + purge + atomic write"
"""ZIP package helpers for portable ``.imgsli`` project files.

Layout::

    project.json
    preview.png (optional canvas-grab thumbnail; legacy packages may use preview.jpg)
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
CACHE_PREFIX = "cache/"
ASSET_ID_LEN = 16

# Desktop-calibrated decompression caps (W3.2): a ~10 MB zip must not expand
# to hundreds of GB. These are generous for legitimate large images
# (20000x20000 raw ~1.6 GB) but block zip-bombs / GNOME thumbnailer abuse.
ZIP_MAX_PROJECT_JSON_BYTES = 16 * 1024 * 1024
ZIP_MAX_PREVIEW_BYTES = 32 * 1024 * 1024
ZIP_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB per member
ZIP_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB cumulative

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


def cache_member_path(asset_id: str) -> str:
    return f"{CACHE_PREFIX}{asset_id}/pixels.raw"


def embed_pixel_cache_sources(
    sources_by_path: dict[str, tuple[Any, int, int]],
    path_to_member: dict[str, str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Remap ``{abs_path: (open fd, width, height)}`` through ``path_to_member``.

    ``path_to_member`` only has entries for paths that were actually embedded
    as media (``embed_media`` skips missing/unreadable files), so a source
    whose path isn't in it is not embeddable — its fd is closed and it is
    dropped. Returns ``({cache_member: open fd}, {asset_id: catalog entry})``.
    """
    from core.constants import AppConstants

    cache_members: dict[str, Any] = {}
    catalog: dict[str, dict[str, Any]] = {}
    for path, (fd, width, height) in sources_by_path.items():
        member = path_to_member.get(path)
        if member is None or not member.startswith(MEDIA_PREFIX):
            try:
                fd.close()
            except Exception:
                pass
            continue
        asset_id = member[len(MEDIA_PREFIX):].split("/", 1)[0]
        cache_member = cache_member_path(asset_id)
        cache_members[cache_member] = fd
        try:
            size = os.fstat(fd.fileno()).st_size
        except OSError:
            size = int(width) * int(height) * 4
        catalog[asset_id] = {
            "member": cache_member,
            "width": int(width),
            "height": int(height),
            "tile_size": int(AppConstants.PIXEL_TILE_SIZE),
            "bytes": size,
        }
    return cache_members, catalog


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
    preview_png: bytes | None = None,
    preview_jpeg: bytes | None = None,
    cache_members: dict[str, Any] | None = None,
) -> None:
    """Atomically write a ZIP project containing ``project.json`` + media.

    Optional ``preview_png`` is stored as top-level ``preview.png`` (active
    workspace canvas grab; see ``project_preview.capture_project_preview_png``).
    ``preview_jpeg`` is accepted as a deprecated alias for the same bytes.
    ``cache_members`` is ``{cache/<asset_id>/pixels.raw: open fd}`` — raw
    RGBA8 buffers, streamed via ``copyfileobj`` (sources are open fds, not
    filesystem paths) and stored uncompressed since RGBA noise doesn't
    compress. Every fd is closed once written, even on failure.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Reverse map: member -> first absolute source
    member_to_source: dict[str, Path] = {}
    for abs_path, member in path_to_member.items():
        member_to_source.setdefault(member, Path(abs_path))

    members = sorted(member_to_source.keys())
    cache_members = cache_members or {}
    cache_member_names = sorted(cache_members.keys())
    preview_bytes = preview_png if preview_png is not None else preview_jpeg
    has_preview = bool(preview_bytes)
    total = len(members) + len(cache_member_names) + 1 + (1 if has_preview else 0)

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

                if preview_bytes is not None:
                    zf.writestr(PREVIEW_MEMBER, preview_bytes)
                done += 1
                if progress is not None:
                    progress(done, total, PREVIEW_MEMBER)
            for index, member in enumerate(members, start=done + 1):
                source = member_to_source[member]
                if progress is not None:
                    progress(index - 1, total, str(source))
                zf.write(source, arcname=member)
            done += len(members)
            for index, member in enumerate(cache_member_names, start=done + 1):
                source_fd = cache_members[member]
                if progress is not None:
                    progress(index - 1, total, member)
                zinfo = zipfile.ZipInfo(member)
                zinfo.compress_type = zipfile.ZIP_STORED
                try:
                    with zf.open(zinfo, "w") as dest_stream:
                        shutil.copyfileobj(source_fd, dest_stream)
                finally:
                    try:
                        source_fd.close()
                    except Exception:
                        pass
            if progress is not None:
                progress(total, total, "")
        os.replace(tmp_path, dest)
    except Exception:
        for source_fd in cache_members.values():
            try:
                source_fd.close()
            except Exception:
                pass
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _capped_copy(src, dst, limit: int, member: str) -> int:
    """Copy src->dst, aborting if *limit* bytes exceeded. Returns bytes copied."""
    copied = 0
    chunk = 1024 * 1024
    while True:
        buf = src.read(chunk)
        if not buf:
            break
        copied += len(buf)
        if copied > limit:
            raise ValueError(
                f"Zip member {member!r} exceeds per-member limit ({limit} bytes)"
            )
        dst.write(buf)
    return copied


def read_project_json_from_zip(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path, "r") as zf:
        try:
            info = zf.getinfo(PROJECT_JSON_NAME)
            if info.file_size > ZIP_MAX_PROJECT_JSON_BYTES:
                raise ValueError(
                    f"{PROJECT_JSON_NAME} too large ({info.file_size} bytes > {ZIP_MAX_PROJECT_JSON_BYTES})"
                )
        except KeyError:
            pass
        with zf.open(PROJECT_JSON_NAME) as fh:
            # Stream with cap rather than unbounded read()
            import io

            buf = io.BytesIO()
            _capped_copy(fh, buf, ZIP_MAX_PROJECT_JSON_BYTES, PROJECT_JSON_NAME)
            return json.loads(buf.getvalue().decode("utf-8"))


def _is_within_directory(base: Path, target: Path) -> bool:
    try:
        return target.resolve().is_relative_to(base.resolve())
    except AttributeError:
        # Python <3.9 fallback
        try:
            target.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            return False
    except ValueError:
        return False


def _atomic_extract_member(
    zf: zipfile.ZipFile, member: str, target: Path, *, per_member_limit: int | None = None
) -> None:
    """Extract *member* to *target* atomically via tmp+rename, capped per-member."""
    if per_member_limit is None:
        per_member_limit = ZIP_MAX_MEMBER_BYTES
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.tmp"
    # Ensure stale tmp from a crashed previous extraction does not confuse.
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    # Pre-check declared size before decompressing (cheap rejection for zip-bomb).
    try:
        info = zf.getinfo(member)
        if info.file_size > per_member_limit:
            raise ValueError(
                f"Zip member {member!r} too large ({info.file_size} bytes > {per_member_limit})"
            )
    except KeyError:
        pass
    with zf.open(member) as src, tmp.open("wb") as dst:
        _capped_copy(src, dst, per_member_limit, member)
    # Verify non-truncated extraction before publishing.
    try:
        info = zf.getinfo(member)
        expected = info.file_size
        actual = tmp.stat().st_size
        if actual != expected:
            raise IOError(f"Truncated extraction for {member}: expected {expected} got {actual}")
    except KeyError:
        pass
    os.replace(tmp, target)


def purge_old_project_caches(current_cache_dir: Path, keep: int = 5, max_age_days: int = 7) -> int:
    """Delete stale ``projects/<hash>`` dirs, keeping *keep* newest.

    Every save changes the ``path:mtime`` hash, stranding a full copy. This
    purges siblings of *current_cache_dir* older than *max_age_days* or beyond
    the *keep* newest quota. Returns number of dirs removed.
    """
    import time

    projects_root = Path(current_cache_dir).parent
    if not projects_root.is_dir():
        return 0
    try:
        entries = [p for p in projects_root.iterdir() if p.is_dir()]
    except OSError:
        return 0
    # Sort newest first by mtime.
    entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    now = time.time()
    max_age_sec = max_age_days * 86400
    removed = 0
    for idx, entry in enumerate(entries):
        if entry.resolve() == current_cache_dir.resolve():
            continue
        is_old = (now - entry.stat().st_mtime) > max_age_sec if entry.exists() else False
        beyond_keep = idx >= keep
        if is_old or beyond_keep:
            try:
                shutil.rmtree(entry)
                removed += 1
                logger.debug("Purged old project cache %s", entry)
            except OSError as exc:
                logger.debug("Failed to purge %s: %s", entry, exc)
    return removed


def extract_media(
    path: str | Path,
    cache_dir: Path,
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    """Extract ``media/`` members to ``cache_dir``.

    Returns ``{package_relative_member: absolute_cache_path}``.
    Reuses existing files only when size matches the catalog/ZIP entry;
    otherwise re-extracts atomically via tmp+rename to avoid truncated files
    being reused forever. Also purges old project caches.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    cumulative = 0
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
            # Pre-check cumulative budget using declared sizes
            try:
                info = zf.getinfo(member)
                cumulative += info.file_size
                if cumulative > ZIP_MAX_TOTAL_BYTES:
                    raise ValueError(
                        f"Total extracted media exceeds cumulative limit ({ZIP_MAX_TOTAL_BYTES} bytes)"
                    )
            except KeyError:
                pass
            target = (cache_dir / member).resolve()
            if not _is_within_directory(cache_dir, target):
                raise ValueError(f"Unsafe zip member path: {member}")
            # Reuse only when size matches ZIP entry (catalog bytes); a
            # crash/disk-full can leave a partial file that st_size>0 would
            # previously have trusted forever.
            if target.is_file():
                try:
                    info = zf.getinfo(member)
                    if target.stat().st_size == info.file_size:
                        mapping[member] = str(target)
                        continue
                    logger.debug("Re-extracting %s: size mismatch %s != %s", member, target.stat().st_size, info.file_size)
                except KeyError:
                    if target.stat().st_size > 0:
                        mapping[member] = str(target)
                        continue
            _atomic_extract_member(zf, member, target)
            mapping[member] = str(target)
        if progress is not None and total:
            progress(total, total, "")
    # Best-effort purge of stale sibling project caches.
    try:
        purge_old_project_caches(cache_dir)
    except Exception:
        logger.debug("purge_old_project_caches failed", exc_info=True)
    return mapping


def extract_pixel_cache(
    path: str | Path,
    cache_dir: Path,
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    """Extract ``cache/`` members (embedded pixel-cache buffers) to ``cache_dir``.

    Returns ``{asset_id: absolute_cache_path}``. Atomic + size-checked like
    :func:`extract_media`.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    cumulative = 0
    with zipfile.ZipFile(path, "r") as zf:
        members = [
            name
            for name in zf.namelist()
            if name.startswith(CACHE_PREFIX) and not name.endswith("/")
        ]
        total = len(members)
        for index, member in enumerate(members):
            if progress is not None:
                progress(index, total, member)
            try:
                info = zf.getinfo(member)
                cumulative += info.file_size
                if cumulative > ZIP_MAX_TOTAL_BYTES:
                    raise ValueError(
                        f"Total extracted pixel cache exceeds cumulative limit ({ZIP_MAX_TOTAL_BYTES} bytes)"
                    )
            except KeyError:
                pass
            target = (cache_dir / member).resolve()
            if not _is_within_directory(cache_dir, target):
                raise ValueError(f"Unsafe zip member path: {member}")
            asset_id = member[len(CACHE_PREFIX):].split("/", 1)[0]
            if target.is_file():
                try:
                    info = zf.getinfo(member)
                    if target.stat().st_size == info.file_size:
                        mapping[asset_id] = str(target)
                        continue
                except KeyError:
                    if target.stat().st_size > 0:
                        mapping[asset_id] = str(target)
                        continue
            _atomic_extract_member(zf, member, target)
            mapping[asset_id] = str(target)
        if progress is not None and total:
            progress(total, total, "")
    return mapping
