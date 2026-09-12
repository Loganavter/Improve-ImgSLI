"""Busy-cursor and toast progress plumbing for project open/save."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo

logger = logging.getLogger("ImproveImgSLI")


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


def _begin_project_busy(owner: "MainWindowProjectIo", message: str):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    toast = owner._project_toast_manager()
    toast_id = None
    if toast is not None:
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
