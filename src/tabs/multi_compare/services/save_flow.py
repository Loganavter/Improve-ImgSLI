"""Background save-flow coordinator for the Multi Compare tab.

Mirrors :class:`tabs.image_compare.services.export_save_flow.ExportSaveFlowCoordinator`:
GPU compositing stays on the GUI thread (QRhi requires it), but PIL encoding
and the disk write run on a worker thread via ``GenericWorker`` so a slow
``pil_image.save()`` (e.g. large PNG) never freezes the UI. Progress and
outcome are reported through the same toast-notification mechanism.
"""

from __future__ import annotations

import logging
import os
import threading

from PIL import Image
from sli_ui_toolkit.workers import GenericWorker

from tabs.multi_compare.services.image_export import save_composite

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareSaveFlowCoordinator:
    def __init__(self, main_window_app, tr_func, thread_pool=None):
        self.main_window_app = main_window_app
        self.tr = tr_func
        self._thread_pool = thread_pool
        self._save_cancellation: dict[int, threading.Event] = {}
        self._save_workers: dict[int, GenericWorker] = {}
        self._save_task_counter = 0

    def _get_toast_manager(self):
        return getattr(self.main_window_app, "toast_manager", None)

    def _get_thread_pool(self):
        return self._thread_pool or getattr(self.main_window_app, "thread_pool", None)

    def _next_save_task_id(self) -> int:
        self._save_task_counter += 1
        return self._save_task_counter

    def _update_toast_safe(
        self,
        save_task_id: int | None,
        message: str,
        *,
        success: bool,
        duration: int = 0,
        progress: int | None = None,
        actions=None,
    ) -> None:
        toast_manager = self._get_toast_manager()
        if toast_manager is None or save_task_id is None:
            return
        try:
            kwargs = {
                "success": success,
                "duration": duration,
                "progress": progress,
            }
            if actions is not None:
                kwargs["actions"] = actions
            toast_manager.update_toast(
                save_task_id,
                message,
                **kwargs,
            )
        except Exception as exc:
            logger.error("Toast update failed for %s: %s", save_task_id, exc)

    def start_save_worker(self, pil_image: Image.Image, options: dict) -> None:
        """``pil_image`` must already be a plain ``PIL.Image`` (converted on the
        GUI thread) — never pass a ``QImage`` here, see ``image_export.py``."""
        final_path_for_display = self._build_display_path(options)
        save_task_id, cancel_event = self._create_save_toast(final_path_for_display)

        worker = GenericWorker(
            self._save_worker_task,
            pil_image=pil_image,
            options=options,
            cancel_event=cancel_event,
        )
        worker.kwargs["progress_callback"] = worker.signals.progress
        self._save_workers[save_task_id] = worker
        worker.signals.progress.connect(
            lambda value: self._on_save_worker_progress(
                save_task_id,
                final_path_for_display,
                value,
            )
        )
        worker.signals.result.connect(
            lambda out_path: self._on_save_worker_done(
                save_task_id,
                cancel_event,
                out_path,
            )
        )
        worker.signals.error.connect(
            lambda err_tuple: self._on_save_worker_error(
                save_task_id,
                cancel_event,
                final_path_for_display,
                err_tuple,
            )
        )
        thread_pool = self._get_thread_pool()
        if thread_pool is None:
            logger.warning(
                "[mc-save] no thread_pool available, saving synchronously on GUI thread"
            )
            self._finalize_save_worker(save_task_id)
            save_composite(pil_image, options)
            return
        thread_pool.start(worker)

    def _save_worker_task(self, **kwargs):
        pil_image = kwargs["pil_image"]
        options = kwargs["options"]
        cancel_event = kwargs.get("cancel_event")
        progress_callback = kwargs.get("progress_callback")

        def emit_progress(value: int) -> None:
            if progress_callback:
                progress_callback.emit(value)

        try:
            return save_composite(
                pil_image,
                options,
                cancel_event=cancel_event,
                progress_callback=emit_progress,
            )
        except RuntimeError as e:
            if str(e) == "Save canceled by user":
                return None
            raise
        except Exception as e:
            logger.error("[mc-save] worker task failed: %s", e, exc_info=True)
            raise

    def cancel_all_exports(self) -> None:
        for save_task_id, cancel_event in list(self._save_cancellation.items()):
            if cancel_event:
                cancel_event.set()
                logger.info("[mc-save] export %s canceled", save_task_id)
        for save_task_id in list(self._save_cancellation.keys()):
            self._update_toast_safe(
                save_task_id,
                self.tr("msg.saving_canceled", "Canceled"),
                success=False,
                duration=2000,
            )
        self._save_cancellation.clear()
        self._save_workers.clear()

    def _build_display_path(self, options: dict) -> str:
        fmt_disp = (options.get("format", "PNG") or "PNG").upper()
        ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
        return os.path.join(
            options["output_dir"],
            f"{options['file_name']}{ext_disp}",
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
        self,
        final_path_for_display: str,
    ) -> tuple[int, threading.Event]:
        toast_path_line = self._build_toast_path_line(final_path_for_display)
        toast_message = f"{self.tr('msg.saving', 'Saving')}\n{toast_path_line}..."
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
                self.tr("msg.saving_canceled", "Canceled"),
                success=False,
                duration=3000,
            )

        if toast_manager is None:
            toast_id = self._next_save_task_id()
            logger.info(
                "[mc-save] toast manager unavailable; continuing export without toast UI"
            )
        else:
            toast_id = toast_manager.show_toast(
                toast_message,
                duration=0,
                actions=[(self.tr("common.cancel", "Cancel"), on_cancel)],
                progress=0,
            )
        cancel_ctx["id"] = toast_id
        self._save_cancellation[toast_id] = cancel_event
        return toast_id, cancel_event

    def _on_save_worker_done(
        self,
        save_task_id: int,
        cancel_event: threading.Event,
        out_path: str | None,
    ) -> None:
        if cancel_event.is_set():
            return
        if not out_path:
            self._finalize_save_worker(save_task_id)
            return

        success_message = f"{self.tr('msg.saved', 'Saved')} {os.path.basename(out_path)}"
        self._update_toast_safe(
            save_task_id,
            success_message,
            success=True,
            duration=4000,
            progress=100,
            actions=[],
        )
        self._finalize_save_worker(save_task_id)

    def _on_save_worker_progress(
        self,
        save_task_id: int,
        final_path_for_display: str,
        progress: int,
    ) -> None:
        if save_task_id not in self._save_cancellation:
            return
        toast_path_line = self._build_toast_path_line(final_path_for_display)
        toast_message = f"{self.tr('msg.saving', 'Saving')}\n{toast_path_line}..."
        self._update_toast_safe(
            save_task_id,
            toast_message,
            success=False,
            duration=0,
            progress=progress,
        )

    def _on_save_worker_error(
        self,
        save_task_id: int,
        cancel_event: threading.Event,
        final_path_for_display: str,
        _err_tuple,
    ) -> None:
        if not cancel_event.is_set():
            error_message = f"{self.tr('msg.error_saving', 'Error saving')} {final_path_for_display}"
            self._update_toast_safe(
                save_task_id,
                error_message,
                success=False,
                duration=5000,
            )
        self._finalize_save_worker(save_task_id)

    def _finalize_save_worker(self, save_task_id: int) -> None:
        self._save_cancellation.pop(save_task_id, None)
        self._save_workers.pop(save_task_id, None)
