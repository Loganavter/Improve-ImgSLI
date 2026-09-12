"""Shared external-file DnD helper — single place for image accept/extract.

Window-level ``hasUrls → isLocalFile → toLocalFile`` is tricky (http URLs
give ``""``, ``file://`` with ``%20`` needs decode, directories must be
accepted even without extension). Gallery had a copy missing ``isLocalFile()``
(fixed 2026-08-26 wave). Per ``docs/dev/ARCHITECTURE.md:252`` reusable image
primitives belong in ``shared/`` (not ``core/``).

This module owns only the *file-extraction* part:

* ``extract_image_paths_from_mime(mime)`` — ``list[Path]`` of local image
  files + directories that are acceptable for triage.
* ``has_acceptable_image_drop(mime)`` — preview for ``dragEnter``.

Both use ``shared/image_extensions.is_accepted_image_path`` and
``QUrl.isLocalFile()``/``toLocalFile()`` (Qt docs
``QMimeData::urls()`` + ``QUrl::isLocalFile``). Remote ``http://`` URLs
are intentionally ignored for folder-drop (paste path handles them via
``shared/clipboard_images.py`` download).
"""

from __future__ import annotations

from pathlib import Path

from shared.image_extensions import is_accepted_image_path


def _local_paths_from_mime(mime) -> list[Path]:
    """Return raw local ``Path``s from ``mime.urls()`` (file + dir)."""
    if mime is None or not mime.hasUrls():
        return []
    out: list[Path] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        local = url.toLocalFile()
        if not local:
            continue
        out.append(Path(local))
    # Fallback: some managers put file:// list in text/uri-list text
    if not out:
        try:
            raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
            for line in raw.splitlines():
                line = line.strip()
                if not line.startswith("file:"):
                    continue
                from PySide6.QtCore import QUrl

                q = QUrl(line)
                if q.isLocalFile():
                    loc = q.toLocalFile()
                    if loc:
                        out.append(Path(loc))
        except Exception:
            pass
    return out


def has_acceptable_image_drop(mime) -> bool:
    """True if mime contains at least one acceptable image or directory."""
    for p in _local_paths_from_mime(mime):
        try:
            if p.is_dir() or is_accepted_image_path(p):
                return True
        except Exception:
            continue
    return False


def extract_image_paths_from_mime(mime) -> list[Path]:
    """Extract acceptable image files and directories from mime.

    Returns only existing paths where ``is_dir()`` or
    ``is_accepted_image_path`` holds. Caller decides file-vs-dir routing
    (gallery: ``all_files and not has_dir`` → ``open_paths`` else folder).
    """
    raw = _local_paths_from_mime(mime)
    out: list[Path] = []
    for p in raw:
        try:
            if not p.exists():
                continue
            if p.is_dir() or is_accepted_image_path(p):
                out.append(p)
        except Exception:
            continue
    return out
