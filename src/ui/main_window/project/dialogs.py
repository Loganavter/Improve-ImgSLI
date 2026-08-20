"""Native open/save file-dialog prompts for project files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo


def _choose_project_open_path(owner: "MainWindowProjectIo") -> str | None:
    """Native save/open dialogs use the desktop portal on Flatpak/Wayland."""
    path, _ = QFileDialog.getOpenFileName(
        owner._window,
        owner._tr("menu.open_project", "Open Project"),
        owner.project_start_path(for_save=False),
        owner._tr(
            "menu.project_filter",
            "Improve ImgSLI Project (*.imgsli)",
        ),
    )
    return path or None


def _choose_project_save_path(owner: "MainWindowProjectIo") -> str | None:
    from services.io.project_io import PROJECT_FILE_EXTENSION

    path, _ = QFileDialog.getSaveFileName(
        owner._window,
        owner._tr("menu.save_project_as", "Save Project As…"),
        owner.project_start_path(for_save=True),
        owner._tr(
            "menu.project_filter",
            "Improve ImgSLI Project (*.imgsli)",
        ),
    )
    if not path:
        return None
    lower = path.lower()
    if not lower.endswith(PROJECT_FILE_EXTENSION) and not lower.endswith(".imgsli-project"):
        path = f"{path}{PROJECT_FILE_EXTENSION}"
    return path
