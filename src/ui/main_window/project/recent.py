"""Recent-project list and active-session title sync."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo

logger = logging.getLogger("ImproveImgSLI")


def resolve_session_picker_host_chrome():
    """Session-picker host extension, or ``None`` if the page is not ready."""
    try:
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE
        from tabs.registry import TabRegistry

        return TabRegistry().create_service_for(
            INITIAL_WORKSPACE_SESSION_TYPE,
            "session_picker.host_chrome",
        )
    except Exception:
        logger.exception("Failed to resolve session picker host chrome")
        return None


def remember_project_path(owner: "MainWindowProjectIo", path: str) -> None:
    from pathlib import Path

    from services.io.recent_projects import (
        notify_recent_cap_eviction,
        record_recent_project,
    )

    owner.current_project_path = path
    settings = owner.project_settings()
    settings.setValue("project_last_path", path)
    settings.setValue("project_last_dir", str(Path(path).parent))
    settings.sync()
    try:
        result = record_recent_project(path, settings=settings)
        notify_recent_cap_eviction(
            result.evicted,
            toast_manager=owner._project_toast_manager(),
        )
    except Exception:
        logger.exception("Failed to record recent project")
    owner._apply_project_name_to_active_session(path)
    owner.refresh_session_picker_recent()


def _apply_project_name_to_active_session(owner: "MainWindowProjectIo", path: str) -> None:
    """Rename the active workspace tab to the project basename."""
    from pathlib import Path

    from core.store import INITIAL_WORKSPACE_SESSION_TYPE

    stem = Path(path).stem.strip()
    if not stem:
        return
    try:
        store = getattr(owner._window, "store", None)
        if store is None:
            return
        session = store.get_active_workspace_session()
        if session is None:
            return
        if getattr(session, "session_type", "") == INITIAL_WORKSPACE_SESSION_TYPE:
            return
        session_id = getattr(session, "id", None)
        if not session_id:
            return
        if (getattr(session, "title", "") or "") == stem:
            return
        store.rename_workspace_session(session_id, stem)
    except Exception:
        logger.exception("Failed to rename session after project save")


def refresh_session_picker_recent(owner: "MainWindowProjectIo") -> None:
    chrome = resolve_session_picker_host_chrome()
    if chrome is None:
        return
    try:
        chrome.refresh_recent()
    except Exception:
        logger.exception("Failed to refresh session picker recent panel")


def wire_session_picker_recent(owner: "MainWindowProjectIo") -> None:
    """Attach open-project handler to the Session Picker recent panel."""
    chrome = resolve_session_picker_host_chrome()
    if chrome is None:
        return
    chrome.set_open_project_handler(owner.open_project_at_path)
