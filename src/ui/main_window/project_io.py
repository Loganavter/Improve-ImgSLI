"""Host project open/save flow for the main window.

Owns path sticky defaults, async load/save workers, recent-list wiring, and
toast progress. Title-bar menus and Find Action runners stay in
``menu_controller`` and call into this class.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import QFileDialog

if TYPE_CHECKING:
    from ui.main_window.window import MainWindow

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


class MainWindowProjectIo:
    """File → Open / Save / Save As and Session Picker recent open."""

    def __init__(
        self,
        window: MainWindow,
        *,
        tr: Callable[[str, str], str],
    ) -> None:
        self._window = window
        self._tr = tr
        self.current_project_path: str | None = None
        self._project_worker = None

    def _presenter(self):
        return getattr(self._window, "presenter", None)

    def project_settings(self):
        from PySide6.QtCore import QSettings

        return QSettings("improve-imgsli", "improve-imgsli")

    def _default_documents_dir(self) -> str:
        import os

        from PySide6.QtCore import QStandardPaths

        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        if documents and os.path.isdir(documents):
            return documents
        return os.path.expanduser("~")

    def _is_downloads_dir(self, path: str) -> bool:
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

    def project_start_path(self, *, for_save: bool) -> str:
        """Directory (open) or full suggested path (save) for the file dialog."""
        import os
        from pathlib import Path

        from services.io.project_io import PROJECT_FILE_EXTENSION

        settings = self.project_settings()
        last_path = str(settings.value("project_last_path", "") or "")
        last_dir = str(settings.value("project_last_dir", "") or "")
        if not last_dir and last_path:
            last_dir = str(Path(last_path).parent)
        documents = self._default_documents_dir()
        # Earlier builds defaulted projects into Downloads; never reopen that
        # as the sticky folder for a fresh Save As.
        if last_dir and self._is_downloads_dir(last_dir):
            last_dir = ""
        if not last_dir or not os.path.isdir(last_dir):
            last_dir = documents
        if not for_save:
            return last_dir

        from shared.image_processing.pil_save import next_available_path

        stem = self._custom_session_save_stem() or self._tr(
            "menu.project_untitled", "Untitled"
        )
        current = (self.current_project_path or "").strip()
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
                self._project_path_for_stem(
                    current_path.parent, stem, current=current_path
                )
            )

        # Unbound Save As always starts in Documents — not the last export /
        # Downloads folder left over from older sessions.
        suggested = next_available_path(
            Path(documents) / f"{stem}{PROJECT_FILE_EXTENSION}",
            style="paren",
        )
        return str(suggested)

    def _custom_session_save_stem(self) -> str | None:
        """Filesystem-safe stem from a user-renamed active tab, else None."""
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE
        from domain.workspace import WorkspaceState
        from shared.image_processing.pil_save import sanitize_filename_component

        try:
            store = getattr(self._window, "store", None)
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

    def _project_path_for_stem(self, directory, stem: str, *, current=None):
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

    def reconcile_save_path_with_session_title(self, path: str) -> str:
        """If the active tab was renamed, retarget Save to that basename."""
        from pathlib import Path

        stem = self._custom_session_save_stem()
        if not stem:
            return path
        current = Path(path)
        if current.stem == stem:
            return path
        return str(self._project_path_for_stem(current.parent, stem, current=current))

    def remember_project_path(self, path: str) -> None:
        from pathlib import Path

        from services.io.recent_projects import record_recent_project

        self.current_project_path = path
        settings = self.project_settings()
        settings.setValue("project_last_path", path)
        settings.setValue("project_last_dir", str(Path(path).parent))
        settings.sync()
        try:
            record_recent_project(path, settings=settings)
        except Exception:
            logger.exception("Failed to record recent project")
        self._apply_project_name_to_active_session(path)
        self.refresh_session_picker_recent()

    def _apply_project_name_to_active_session(self, path: str) -> None:
        """Rename the active workspace tab to the project basename."""
        from pathlib import Path

        from core.store import INITIAL_WORKSPACE_SESSION_TYPE

        stem = Path(path).stem.strip()
        if not stem:
            return
        try:
            store = getattr(self._window, "store", None)
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

    def refresh_session_picker_recent(self) -> None:
        chrome = resolve_session_picker_host_chrome()
        if chrome is None:
            return
        try:
            chrome.refresh_recent()
        except Exception:
            logger.exception("Failed to refresh session picker recent panel")

    def wire_session_picker_recent(self) -> None:
        """Attach open-project handler to the Session Picker recent panel."""
        chrome = resolve_session_picker_host_chrome()
        if chrome is None:
            return
        chrome.set_open_project_handler(self.open_project_at_path)

    def _choose_project_open_path(self) -> str | None:
        """Native save/open dialogs use the desktop portal on Flatpak/Wayland."""
        path, _ = QFileDialog.getOpenFileName(
            self._window,
            self._tr("menu.open_project", "Open Project"),
            self.project_start_path(for_save=False),
            self._tr(
                "menu.project_filter",
                "Improve ImgSLI Project (*.imgsli)",
            ),
        )
        return path or None

    def _choose_project_save_path(self) -> str | None:
        from services.io.project_io import PROJECT_FILE_EXTENSION

        path, _ = QFileDialog.getSaveFileName(
            self._window,
            self._tr("menu.save_project_as", "Save Project As…"),
            self.project_start_path(for_save=True),
            self._tr(
                "menu.project_filter",
                "Improve ImgSLI Project (*.imgsli)",
            ),
        )
        if not path:
            return None
        lower = path.lower()
        if not lower.endswith(PROJECT_FILE_EXTENSION) and not lower.endswith(
            ".imgsli-project"
        ):
            path = f"{path}{PROJECT_FILE_EXTENSION}"
        return path

    def _current_save_path(self) -> str | None:
        """Path for silent Save, or None when Save should fall through to Save As."""
        from pathlib import Path

        from services.io.project_io import PROJECT_FILE_EXTENSION

        path = (self.current_project_path or "").strip()
        if not path:
            return None
        suffix = Path(path).suffix.lower()
        if suffix not in {PROJECT_FILE_EXTENSION, ".imgsli-project"}:
            return None
        return path

    def _project_toast_manager(self):
        return getattr(self._window, "toast_manager", None)

    def _project_thread_pool(self):
        pool = getattr(self._window, "thread_pool", None)
        if pool is not None:
            return pool
        presenter = self._presenter()
        controller = getattr(presenter, "main_controller", None) if presenter else None
        return getattr(controller, "thread_pool", None) if controller else None

    def _show_project_error(self, title: str, text: str) -> None:
        from shared_toolkit.ui.message_dialog import AppMessageDialog

        AppMessageDialog.warning(self._window, title=title, text=text)

    def _begin_project_busy(self, message: str):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        toast = self._project_toast_manager()
        toast_id = None
        if toast is not None:
            try:
                toast_id = toast.show_toast(message, duration=0, progress=0)
            except Exception:
                logger.exception("Failed to show project progress toast")
                toast_id = None
        return toast, toast_id

    def _end_project_busy(self, toast, toast_id, message: str, *, ok: bool) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.restoreOverrideCursor()
        if toast is None or toast_id is None:
            return
        try:
            if ok:
                toast.update_toast(
                    toast_id, message, success=True, duration=1800, progress=100
                )
            else:
                toast.close_toast(toast_id)
        except Exception:
            logger.exception("Failed to finish project progress toast")

    def _on_project_toast_progress(self, toast, toast_id, message: str, value) -> None:
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

    def open_project(self) -> None:
        path = self._choose_project_open_path()
        if not path:
            return
        self.open_project_at_path(path)

    def open_project_at_path(self, path: str) -> None:
        """Load a project file (File → Open and Session Picker recent)."""
        if not path:
            return
        from pathlib import Path

        if not Path(path).is_file():
            self._handle_missing_project_file(path)
            return

        window = self._window
        presenter = self._presenter()
        controller = getattr(presenter, "main_controller", None) if presenter else None
        if controller is None:
            return

        opening = self._tr("menu.project_opening", "Opening project…")
        toast, toast_id = self._begin_project_busy(opening)
        pool = self._project_thread_pool()

        def _apply_loaded(payload) -> None:
            from services.io.project_io import load_project_data
            from tabs.registry import TabRegistry

            data, warnings = payload
            try:
                load_project_data(
                    data,
                    controller.workspace,
                    window.store,
                    TabRegistry(),
                    replace_workspace=True,
                )
                self.remember_project_path(path)
                self._end_project_busy(toast, toast_id, opening, ok=True)
                if warnings:
                    self._show_project_error(
                        self._tr("menu.open_project", "Open Project"),
                        "\n".join(warnings),
                    )
            except Exception as exc:
                logger.exception("Open project apply failed")
                self._end_project_busy(toast, toast_id, opening, ok=False)
                self._show_project_error(
                    self._tr("menu.open_project", "Open Project"),
                    self._tr(
                        "menu.project_open_failed",
                        "Could not open the project file.",
                    )
                    + f"\n{exc}",
                )

        def _on_error(err_tuple) -> None:
            self._end_project_busy(toast, toast_id, opening, ok=False)
            exc = (
                err_tuple[1]
                if isinstance(err_tuple, tuple) and len(err_tuple) > 1
                else err_tuple
            )
            if self._is_missing_project_error(exc):
                self._handle_missing_project_file(path)
                return
            logger.error("Open project failed: %s", exc, exc_info=err_tuple)
            self._show_project_error(
                self._tr("menu.open_project", "Open Project"),
                self._tr(
                    "menu.project_open_failed",
                    "Could not open the project file.",
                )
                + f"\n{exc}",
            )

        def _worker_task(**kwargs):
            from services.io.project_io import prepare_project_file_for_load

            progress_callback = kwargs.get("progress_callback")

            def _progress(done: int, total: int, _label: str) -> None:
                if progress_callback is None or total <= 0:
                    return
                progress_callback.emit(int(100 * done / max(total, 1)))

            return prepare_project_file_for_load(path, progress=_progress)

        if pool is None:
            try:
                from services.io.project_io import prepare_project_file_for_load

                _apply_loaded(prepare_project_file_for_load(path))
            except Exception as exc:
                _on_error((type(exc), exc, None))
            return

        from sli_ui_toolkit.workers import GenericWorker

        worker = GenericWorker(_worker_task)
        worker.kwargs["progress_callback"] = worker.signals.progress
        self._project_worker = worker
        worker.signals.progress.connect(
            lambda value: self._on_project_toast_progress(
                toast, toast_id, opening, value
            )
        )
        worker.signals.result.connect(_apply_loaded)
        worker.signals.error.connect(_on_error)
        pool.start(worker)

    @staticmethod
    def _is_missing_project_error(exc: object) -> bool:
        import errno

        if isinstance(exc, FileNotFoundError):
            return True
        if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOENT:
            return True
        return False

    def _handle_missing_project_file(self, path: str) -> None:
        """Refresh Recent to the missing-card state; avoid a raw exception dialog."""
        from pathlib import Path

        logger.warning("Project file missing: %s", path)
        self.refresh_session_picker_recent()
        name = Path(path).name or path
        message = self._tr(
            "menu.project_file_missing",
            "The project file is missing. The Recent card was updated.",
        )
        toast = self._project_toast_manager()
        if toast is not None:
            try:
                toast.show_toast(f"{message}\n{name}", duration=3200)
                return
            except Exception:
                logger.exception("Failed to show missing-project toast")
        self._show_project_error(
            self._tr("menu.open_project", "Open Project"),
            f"{message}\n{name}",
        )

    def save_project(self) -> None:
        path = self._current_save_path()
        if path is None:
            self.save_project_as()
            return
        path = self.reconcile_save_path_with_session_title(path)
        self.write_project(path)

    def save_project_as(self) -> None:
        path = self._choose_project_save_path()
        if not path:
            return
        self.write_project(path)

    def write_project(self, path: str) -> None:
        window = self._window
        from services.io.project_io import build_project_data
        from services.io.project_package import iter_session_media_paths
        from tabs.registry import TabRegistry

        # Snapshot session state on the UI thread (viewport / widgets).
        try:
            project_data = build_project_data(window.store, TabRegistry())
        except Exception as exc:
            logger.exception("Project snapshot failed")
            self._show_project_error(
                self._tr("menu.save_project", "Save Project"),
                self._tr(
                    "menu.project_save_failed",
                    "Could not save the project file.",
                )
                + f"\n{exc}",
            )
            return

        preview_jpeg = None
        try:
            from services.io.project_preview import capture_project_preview_jpeg

            preview_jpeg = capture_project_preview_jpeg(window)
        except Exception:
            logger.debug("Project preview capture skipped", exc_info=True)

        media_count = len(set(iter_session_media_paths(project_data)))
        logger.info(
            "Saving project to %s (%d unique media path(s))", path, media_count
        )

        saving = self._tr("menu.project_saving", "Saving project…")
        toast, toast_id = self._begin_project_busy(saving)
        pool = self._project_thread_pool()

        def _on_done(missing) -> None:
            self.remember_project_path(path)
            self._end_project_busy(toast, toast_id, saving, ok=True)
            if missing:
                self._show_project_error(
                    self._tr("menu.save_project", "Save Project"),
                    self._tr(
                        "menu.project_missing_media",
                        "Project saved, but some image files were missing and were not embedded.",
                    )
                    + "\n"
                    + "\n".join(list(missing)[:12]),
                )

        def _on_error(err_tuple) -> None:
            self._end_project_busy(toast, toast_id, saving, ok=False)
            exc = (
                err_tuple[1]
                if isinstance(err_tuple, tuple) and len(err_tuple) > 1
                else err_tuple
            )
            logger.exception("Save project failed: %s", exc)
            self._show_project_error(
                self._tr("menu.save_project", "Save Project"),
                self._tr(
                    "menu.project_save_failed",
                    "Could not save the project file.",
                )
                + f"\n{exc}",
            )

        def _worker_task(**kwargs):
            from services.io.project_io import package_project_data

            progress_callback = kwargs.get("progress_callback")

            def _progress(done: int, total: int, _label: str) -> None:
                if progress_callback is None or total <= 0:
                    return
                progress_callback.emit(int(100 * done / max(total, 1)))

            return package_project_data(
                project_data, path, progress=_progress, preview_jpeg=preview_jpeg
            )

        if pool is None:
            try:
                from services.io.project_io import package_project_data

                _on_done(
                    package_project_data(
                        project_data, path, preview_jpeg=preview_jpeg
                    )
                )
            except Exception as exc:
                _on_error((type(exc), exc, None))
            return

        from sli_ui_toolkit.workers import GenericWorker

        worker = GenericWorker(_worker_task)
        worker.kwargs["progress_callback"] = worker.signals.progress
        self._project_worker = worker
        worker.signals.progress.connect(
            lambda value: self._on_project_toast_progress(
                toast, toast_id, saving, value
            )
        )
        worker.signals.result.connect(_on_done)
        worker.signals.error.connect(_on_error)
        pool.start(worker)
