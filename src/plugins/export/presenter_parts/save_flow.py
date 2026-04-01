from __future__ import annotations

import logging
import os
import threading

from PyQt6.QtWidgets import QMessageBox
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class ExportSaveFlowCoordinator:
    def __init__(self, store, main_window_app, ui_manager, tr_func, state_coordinator):
        self.store = store
        self.main_window_app = main_window_app
        self.ui_manager = ui_manager
        self.tr = tr_func
        self.state = state_coordinator
        self._save_cancellation = {}
        self._save_workers = {}

    def _get_toast_manager(self):
        return getattr(self.main_window_app, "toast_manager", None)

    def _next_save_task_id(self) -> int:
        current = int(getattr(self.main_window_app, "save_task_counter", 0) or 0) + 1
        setattr(self.main_window_app, "save_task_counter", current)
        return current

    def _update_toast_safe(
        self,
        save_task_id: int | None,
        message: str,
        *,
        success: bool,
        duration: int = 0,
    ) -> None:
        toast_manager = self._get_toast_manager()
        if toast_manager is None or save_task_id is None:
            return

        try:
            toast_manager.update_toast(
                save_task_id,
                message,
                success=success,
                duration=duration,
            )
        except Exception as exc:
            logger.error("Toast update failed for %s: %s", save_task_id, exc)

    def validate_export_options(self, export_opts: dict) -> bool:
        out_dir = export_opts.get("output_dir")
        out_name = export_opts.get("file_name")
        if out_dir and out_name:
            return True
        self.ui_manager.messages.show_non_modal_message(
            icon=QMessageBox.Icon.Warning,
            title=self.tr("msg.invalid_data"),
            text=self.tr("msg.specify_output_directory_and_file_name"),
        )
        return False

    def show_missing_images_warning(self) -> None:
        self.ui_manager.messages.show_non_modal_message(
            icon=QMessageBox.Icon.Warning,
            title=self.tr("common.warning"),
            text=self.tr("msg.select_both_images_first"),
        )

    def start_save_worker(
        self,
        save_ctx,
        export_opts: dict,
        export_runner,
    ) -> None:
        final_path_for_display = self._build_display_path(export_opts)
        save_task_id, cancel_event = self._create_save_toast(final_path_for_display)

        worker = GenericWorker(
            export_runner,
            store_copy=self.store.copy_for_worker(),
            image1_for_save=save_ctx.image1_for_save,
            image2_for_save=save_ctx.image2_for_save,
            original1_full=save_ctx.original1_full,
            original2_full=save_ctx.original2_full,
            magnifier_drawing_coords=save_ctx.magnifier_coords_for_save,
            render_context=save_ctx.render_context,
            export_options=export_opts,
            cancel_event=cancel_event,
            file_name1_text=self.state.get_current_display_name(1),
            file_name2_text=self.state.get_current_display_name(2),
        )
        self._save_workers[save_task_id] = worker
        worker.signals.result.connect(
            lambda out_path: self._on_save_worker_done(
                save_task_id, cancel_event, out_path
            )
        )
        worker.signals.error.connect(
            lambda err_tuple: self._on_save_worker_error(
                save_task_id, cancel_event, final_path_for_display, err_tuple
            )
        )
        self.main_window_app.thread_pool.start(worker)

    def cancel_all_exports(self):
        logger.debug(
            "Canceling all active exports (count=%s)", len(self._save_cancellation)
        )
        for save_task_id, cancel_event in list(self._save_cancellation.items()):
            if cancel_event:
                cancel_event.set()
                logger.info("Export %s canceled", save_task_id)

        for save_task_id in list(self._save_cancellation.keys()):
            self._update_toast_safe(
                save_task_id,
                self.tr("msg.saving_canceled"),
                success=False,
                duration=2000,
            )

        self._save_cancellation.clear()
        self._save_workers.clear()

    def _build_display_path(self, export_opts: dict) -> str:
        fmt_disp = (export_opts.get("format", "PNG") or "PNG").upper()
        ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
        return os.path.join(
            export_opts["output_dir"], f"{export_opts['file_name']}{ext_disp}"
        )

    def _build_toast_path_line(self, final_path_for_display: str) -> str:
        directory, file_name = os.path.split(final_path_for_display)
        if not directory:
            return file_name

        normalized_dir = os.path.normpath(directory)
        dir_parts = [part for part in normalized_dir.split(os.sep) if part]
        if len(dir_parts) <= 2:
            compact_dir = normalized_dir
        else:
            compact_dir = os.path.join("...", dir_parts[-2], dir_parts[-1])
        return os.path.join(compact_dir, file_name)

    def _create_save_toast(
        self, final_path_for_display: str
    ) -> tuple[int, threading.Event]:
        toast_path_line = self._build_toast_path_line(final_path_for_display)
        toast_message = f"{self.tr('msg.saving')}\n{toast_path_line}..."
        cancel_event = threading.Event()
        cancel_ctx = {"event": cancel_event}
        toast_manager = self._get_toast_manager()

        def on_cancel():
            ev = cancel_ctx.get("event")
            toast_id = cancel_ctx.get("id")
            if ev:
                ev.set()
            self._update_toast_safe(
                toast_id,
                self.tr("msg.saving_canceled"),
                success=False,
                duration=3000,
            )

        if toast_manager is None:
            toast_id = self._next_save_task_id()
            logger.info("Toast manager unavailable; continuing export without toast UI")
        else:
            toast_id = toast_manager.show_toast(
                toast_message,
                duration=0,
                action_text=self.tr("common.cancel"),
                on_action=on_cancel,
            )
        cancel_ctx["id"] = toast_id
        self._save_cancellation[toast_id] = cancel_event
        return toast_id, cancel_event

    def _on_save_worker_done(
        self, save_task_id: int, cancel_event: threading.Event, out_path: str
    ) -> None:
        if cancel_event.is_set():
            return

        if not out_path:
            self._finalize_save_worker(save_task_id)
            return

        success_message = f"{self.tr('msg.saved')} {os.path.basename(out_path)}"
        self._update_toast_safe(
            save_task_id,
            success_message,
            success=True,
            duration=4000,
        )
        try:
            setattr(self.main_window_app, "_last_saved_path", out_path)
            if hasattr(self.main_window_app, "update_tray_actions_visibility"):
                self.main_window_app.update_tray_actions_visibility()
            notifications_enabled = getattr(
                self.store.settings, "system_notifications_enabled", True
            )
            if notifications_enabled:
                image_for_icon = (
                    out_path
                    if isinstance(out_path, str) and os.path.isfile(out_path)
                    else None
                )
                self.main_window_app.notify_system(
                    self.tr("msg.saved"),
                    f"{self.tr('msg.saved')}: {out_path}",
                    image_path=image_for_icon,
                    timeout_ms=4000,
                )
        except Exception as exc:
            logger.error("Save notification failed: %s", exc)
        finally:
            self._finalize_save_worker(save_task_id)

    def _on_save_worker_error(
        self,
        save_task_id: int,
        cancel_event: threading.Event,
        final_path_for_display: str,
        _err_tuple,
    ) -> None:
        if not cancel_event.is_set():
            error_message = (
                f"{self.tr('msg.error_saving')} {final_path_for_display}"
            )
            self._update_toast_safe(
                save_task_id,
                error_message,
                success=False,
                duration=8000,
            )
        self._finalize_save_worker(save_task_id)

    def _finalize_save_worker(self, save_task_id: int) -> None:
        self._save_cancellation.pop(save_task_id, None)
        self._save_workers.pop(save_task_id, None)
