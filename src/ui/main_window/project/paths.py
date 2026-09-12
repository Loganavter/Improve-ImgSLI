"""Project path resolution and sticky-default helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo


def project_settings(owner: "MainWindowProjectIo"):
    from PySide6.QtCore import QSettings

    return QSettings("improve-imgsli", "improve-imgsli")


def _default_documents_dir(owner: "MainWindowProjectIo") -> str:
    import os

    from PySide6.QtCore import QStandardPaths

    documents = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    if documents and os.path.isdir(documents):
        return documents
    return os.path.expanduser("~")


def _is_downloads_dir(owner: "MainWindowProjectIo", path: str) -> bool:
    """True when ``path`` is the OS Downloads folder (legacy sticky default)."""
    import os
    from pathlib import Path

    from PySide6.QtCore import QStandardPaths

    downloads = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DownloadLocation
    )
    if not downloads:
        return False
    try:
        return Path(path).resolve() == Path(downloads).resolve()
    except OSError:
        return os.path.normpath(path) == os.path.normpath(downloads)


def project_start_path(owner: "MainWindowProjectIo", *, for_save: bool) -> str:
    """Directory (open) or full suggested path (save) for the file dialog."""
    import os
    from pathlib import Path

    from services.io.project_io import PROJECT_FILE_EXTENSION

    settings = owner.project_settings()
    last_path = str(settings.value("project_last_path", "") or "")
    last_dir = str(settings.value("project_last_dir", "") or "")
    if not last_dir and last_path:
        last_dir = str(Path(last_path).parent)
    documents = owner._default_documents_dir()
    # Earlier builds defaulted projects into Downloads; never reopen that
    # as the sticky folder for a fresh Save As.
    if last_dir and owner._is_downloads_dir(last_dir):
        last_dir = ""
    if not last_dir or not os.path.isdir(last_dir):
        last_dir = documents
    if not for_save:
        return last_dir

    from shared.image_processing.pil_save import next_available_path

    stem = owner._custom_session_save_stem() or owner._tr(
        "menu.project_untitled", "Untitled"
    )
    current = (owner.current_project_path or "").strip()
    if current and Path(current).suffix.lower() in {
        PROJECT_FILE_EXTENSION,
        ".imgsli-project",
    }:
        current_path = Path(current)
        # Bound Save As: keep the file path when the tab still matches it;
        # if the user renamed the tab, suggest that name in the same folder.
        if current_path.stem == stem:
            return current
        return str(
            owner._project_path_for_stem(current_path.parent, stem, current=current_path)
        )

    # Unbound Save As always starts in Documents — not the last export /
    # Downloads folder left over from older sessions.
    suggested = next_available_path(
        Path(documents) / f"{stem}{PROJECT_FILE_EXTENSION}",
        style="paren",
    )
    return str(suggested)


def _custom_session_save_stem(owner: "MainWindowProjectIo") -> str | None:
    """Filesystem-safe stem from a user-renamed active tab, else None."""
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE
    from domain.workspace import WorkspaceState
    from shared.image_processing.pil_save import sanitize_filename_component

    try:
        store = getattr(owner._window, "store", None)
        if store is None:
            return None
        session = store.get_active_workspace_session()
        if session is None:
            return None
        session_type = getattr(session, "session_type", "") or ""
        if session_type == INITIAL_WORKSPACE_SESSION_TYPE:
            return None
        title = (getattr(session, "title", None) or "").strip()
        if not title or WorkspaceState.is_auto_title(title, session_type):
            return None
        safe = sanitize_filename_component(title).strip(" .")
        return safe or None
    except Exception:
        return None


def _project_path_for_stem(
    owner: "MainWindowProjectIo", directory, stem: str, *, current=None
):
    """Resolve ``directory/stem.ext``, treating ``current`` as non-colliding."""
    from pathlib import Path

    from shared.image_processing.pil_save import next_available_path
    from services.io.project_io import PROJECT_FILE_EXTENSION

    directory = Path(directory)
    current_path = Path(current) if current is not None else None
    candidate = directory / f"{stem}{PROJECT_FILE_EXTENSION}"
    if current_path is not None:
        try:
            if candidate.resolve() == current_path.resolve():
                return current_path
        except OSError:
            if candidate == current_path:
                return current_path
    if not candidate.exists():
        return candidate
    return next_available_path(candidate, style="paren")


def reconcile_save_path_with_session_title(owner: "MainWindowProjectIo", path: str) -> str:
    """If the active tab was renamed, retarget Save to that basename."""
    from pathlib import Path

    stem = owner._custom_session_save_stem()
    if not stem:
        return path
    current = Path(path)
    if current.stem == stem:
        return path
    return str(owner._project_path_for_stem(current.parent, stem, current=current))


def _current_save_path(owner: "MainWindowProjectIo") -> str | None:
    """Path for silent Save, or None when Save should fall through to Save As."""
    from pathlib import Path

    from services.io.project_io import PROJECT_FILE_EXTENSION

    path = (owner.current_project_path or "").strip()
    if not path:
        return None
    suffix = Path(path).suffix.lower()
    if suffix not in {PROJECT_FILE_EXTENSION, ".imgsli-project"}:
        return None
    return path
