"""Busy-cursor and toast progress plumbing for project open/save."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from core.log_names import APP_LOGGER_NAME

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo

logger = logging.getLogger(APP_LOGGER_NAME)


def _project_toast_manager(owner: "MainWindowProjectIo"):
    return getattr(owner._window, "toast_manager", None)


def _project_thread_pool(owner: "MainWindowProjectIo"):
    pool = getattr(owner._window, "thread_pool", None)
    if pool is not None:
        return pool
    presenter = owner._presenter()
    controller = getattr(presenter, "main_controller", None) if presenter else None
    return getattr(controller, "thread_pool", None) if controller else None


def _show_project_error(owner: "MainWindowProjectIo", title: str, text: str) -> None:
    from shared_toolkit.ui.message_dialog import AppMessageDialog

    AppMessageDialog.warning(owner._window, title=title, text=text)


def _notify_project_saved(owner: "MainWindowProjectIo", path: str) -> None:
    """Tray state + system notification after a project is written.

    The save flow used to end in the in-app toast only - and in nothing at all
    when the toast manager had not resolved (owner report 2026-10-28: "кнопка
    сохранить проект не шлёт тост в аппе и в систему"). A project save is the
    same promise as an image export, which already notifies
    (``image_export/save_flow.py::_on_success_notify``).
    """
    import os

    window = owner._window
    actions = getattr(window, "action_registry", None)
    if actions is None:
        return
    try:
        actions.set_last_saved_path(path)
        actions.update_tray_actions_visibility()
    except Exception:
        logger.exception("Project save: tray refresh failed")
    settings = getattr(getattr(window, "store", None), "settings", None)
    if not bool(getattr(settings, "system_notifications_enabled", True)):
        return
    try:
        actions.notify_system(
            owner._tr("msg.saved", "Saved"),
            f"{owner._tr('msg.saved', 'Saved')}: {path}",
            image_path=path if os.path.isfile(path) else None,
            timeout_ms=4000,
        )
    except Exception:
        logger.exception("Project save: system notification failed")


def _begin_project_busy(owner: "MainWindowProjectIo", message: str):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    toast = owner._project_toast_manager()
    toast_id = None
    if toast is None:
        # Silent before: the whole progress surface vanished with the manager.
        logger.warning(
            "Project busy: no toast manager on the window - progress stays invisible"
        )
    else:
        try:
            toast_id = toast.show_toast(message, duration=0, progress=0)
        except Exception:
            logger.exception("Failed to show project progress toast")
            toast_id = None
    return toast, toast_id


def _end_project_busy(
    owner: "MainWindowProjectIo", toast, toast_id, message: str, *, ok: bool
) -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.restoreOverrideCursor()
    if toast is None or toast_id is None:
        return
    try:
        if ok:
            toast.update_toast(toast_id, message, success=True, duration=1800, progress=100)
        else:
            toast.close_toast(toast_id)
    except Exception:
        logger.exception("Failed to finish project progress toast")


def _on_project_toast_progress(
    owner: "MainWindowProjectIo", toast, toast_id, message: str, value
) -> None:
    if toast is None or toast_id is None:
        return
    try:
        progress = int(value) if value is not None else 0
        toast.update_toast(
            toast_id,
            message,
            success=False,
            duration=0,
            progress=max(0, min(100, progress)),
        )
    except Exception:
        pass
