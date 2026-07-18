"""Project-file MIME helpers for Recent panel drag-and-drop."""

from __future__ import annotations

from PySide6.QtCore import QUrl

from services.io.project_io import PROJECT_FILE_EXTENSION

_PROJECT_SUFFIXES = (PROJECT_FILE_EXTENSION, ".imgsli-project")


def is_project_path(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(suffix) for suffix in _PROJECT_SUFFIXES)


def paths_from_mime(mime) -> list[str]:
    paths: list[str] = []
    urls = list(mime.urls()) if mime.hasUrls() else []
    if not urls and mime.hasFormat("text/uri-list"):
        raw = mime.data("text/uri-list").data().decode("utf-8", errors="replace")
        for line in raw.splitlines():
            part = line.strip()
            if part.startswith("file:"):
                urls.append(QUrl(part))
    for url in urls:
        path = url.toLocalFile()
        if path and path not in paths:
            paths.append(path)
    return paths


def project_paths_from_mime(mime) -> list[str]:
    return [path for path in paths_from_mime(mime) if is_project_path(path)]


def mime_has_external_project(event) -> bool:
    """True when the drag is an external drop of one or more .imgsli paths."""
    if event.source() is not None:
        return False
    mime = event.mimeData()
    if mime is None:
        return False
    if not (mime.hasUrls() or mime.hasFormat("text/uri-list")):
        return False
    return bool(project_paths_from_mime(mime))
