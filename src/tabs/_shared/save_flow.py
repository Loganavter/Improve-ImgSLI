"""Shared save-flow coordinator — single source for B1.

Small collaborator object (state-owning: toast slot, worker lifecycle,
progress/error handlers) parameterized for both tabs:

- ``get_thread_pool``: Callable[[], thread_pool | None]
- ``get_toast_manager``: Callable[[], toast_manager | None]
- ``display_path_style``: "paren" (IC ``stem (1).ext``) vs "underscore" (MC ``stem_1.ext``)
  — kept for parity; display path building is identical, the style will
  matter if the coordinator ever needs to predict the final unique path
  (see ``shared.image_processing.pil_save.next_available_path``).
- ``sync_fallback``: when True (MC) a ``None`` pool falls back to
  synchronous GUI-thread ``sync_fn`` instead of error toast.
- ``on_success_notify``: IC's ``set_last_saved_path`` + ``notify_system``.

Both tab coordinators delegate to this object; it owns ``_save_cancellation``
and ``_save_workers``. ``SAVE_CANCELED_MESSAGE`` is imported from the single
source ``shared.image_processing.pil_save`` (re-exported via
``shared.image_processing.export_encoding``).

Live/export parity: this module touches only toast/worker lifecycle, never
diff/render geometry.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from tabs.save_toast import SaveToastMixin

logger = logging.getLogger("ImproveImgSLI")


class SaveFlowCoordinator(SaveToastMixin):
    """State-owning save-flow coordinator shared by IC and MC."""

    def __init__(
        self,
        *,
        get_thread_pool: Callable[[], Any | None],
        get_toast_manager: Callable[[], Any | None],
        tr_func: Callable[..., str],
        display_path_style: str = "paren",
        sync_fallback: bool = False,
        on_success_notify: Callable[[str], None] | None = None,
    ) -> None:
        self._get_thread_pool_fn = get_thread_pool
        self._get_toast_manager_fn = get_toast_manager
        self._tr_func = tr_func
        if display_path_style not in ("paren", "underscore"):
            logger.warning("Unknown display_path_style %r, using 'paren'", display_path_style)
            display_path_style = "paren"
        self.display_path_style = display_path_style
        self.sync_fallback = bool(sync_fallback)
        self._on_success_notify = on_success_notify
        self._save_cancellation: dict[int, threading.Event] = {}
        self._save_workers: dict[int, Any] = {}
        self._save_task_counter = 0

    # --- SaveToastMixin overrides -------------------------------------------------
    def _get_toast_manager(self):  # type: ignore[override]
        try:
            return self._get_toast_manager_fn() if self._get_toast_manager_fn else None
        except Exception:
            logger.debug("get_toast_manager failed", exc_info=True)
            return None

    def _get_thread_pool(self):
        try:
            return self._get_thread_pool_fn() if self._get_thread_pool_fn else None
        except Exception:
            logger.debug("get_thread_pool failed", exc_info=True)
            return None

    # --- helpers ------------------------------------------------------------------
    def _tr(self, key: str, default: str | None = None) -> str:
        try:
            if default is not None:
                try:
                    return self._tr_func(key, default)  # MC style tr(key, default)
                except TypeError:
                    val = self._tr_func(key)
                    return val if val != key else default
            return self._tr_func(key)
        except Exception:
            return default if default is not None else key

    def _next_save_task_id(self) -> int:
        self._save_task_counter += 1
        return self._save_task_counter

    def _build_display_path(self, options: dict) -> str:
        fmt_disp = (options.get("format", "PNG") or "PNG").upper()
        ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
        # display_path_style does not affect the preview path (both tabs join
        # output_dir + file_name + ext identically); it is stored for callers
        # that need to predict the uniquified final path via next_available_path.
        return os.path.join(options["output_dir"], f"{options['file_name']}{ext_disp}")

    # --- toast creation (mirrors both tabs' _create_save_toast) -------------------
    def _create_save_toast(self, final_path_for_display: str) -> tuple[int, threading.Event]:
        toast_path_line = self._build_toast_path_line(final_path_for_display)
        toast_message = f"{self._tr('msg.saving', 'Saving')}\n{toast_path_line}..."
        cancel_event = threading.Event()
        cancel_ctx: dict[str, Any] = {"event": cancel_event}
        toast_manager = self._get_toast_manager()

        def on_cancel():
            ev = cancel_ctx.get("event")
            toast_id = cancel_ctx.get("id")
            if ev is not None:
                try:
                    ev.set()
                except Exception:
                    pass
            self._update_toast_safe(
                toast_id,
                self._tr("msg.saving_canceled", "Canceled"),
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
                actions=[(self._tr("common.cancel", "Cancel"), on_cancel)],
                progress=0,
            )
        cancel_ctx["id"] = toast_id
        self._save_cancellation[toast_id] = cancel_event
        return toast_id, cancel_event

    # --- lifecycle ---------------------------------------------------------------
    def cancel_all_exports(self) -> None:
        logger.debug("Canceling all active exports (count=%s)", len(self._save_cancellation))
        for save_task_id, cancel_event in list(self._save_cancellation.items()):
            if cancel_event is not None:
                try:
                    cancel_event.set()
                except Exception:
                    pass
                logger.info("Export %s canceled", save_task_id)
        for save_task_id in list(self._save_cancellation.keys()):
            self._update_toast_safe(
                save_task_id,
                self._tr("msg.saving_canceled", "Canceled"),
                success=False,
                duration=2000,
            )
        self._save_cancellation.clear()
        self._save_workers.clear()

    def _on_save_worker_done(
        self,
        save_task_id: int,
        cancel_event: threading.Event,
        out_path: str | None,
    ) -> None:
        try:
            if cancel_event.is_set():
                return
        except Exception:
            pass
        if not out_path:
            self._finalize_save_worker(save_task_id)
            return
        success_message = f"{self._tr('msg.saved', 'Saved')} {os.path.basename(out_path)}"
        self._update_toast_safe(
            save_task_id,
            success_message,
            success=True,
            duration=4000,
            progress=100,
            actions=[],
        )
        if self._on_success_notify is not None:
            try:
                self._on_success_notify(out_path)
            except Exception as exc:
                logger.error("Save notification failed: %s", exc, exc_info=True)
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
        toast_message = f"{self._tr('msg.saving', 'Saving')}\n{toast_path_line}..."
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
        try:
            is_canceled = cancel_event.is_set()
        except Exception:
            is_canceled = False
        if not is_canceled:
            error_message = f"{self._tr('msg.error_saving', 'Error saving')} {final_path_for_display}"
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

    # --- generic worker launch ---------------------------------------------------
    def start_with_worker(
        self,
        options: dict,
        worker_factory: Callable[[threading.Event], Any],
        *,
        sync_fn: Callable[[], Any] | None = None,
    ) -> None:
        """Create toast, build worker via *worker_factory(cancel_event)*, wire signals, start.

        *worker_factory* must return a ``GenericWorker`` (or alike with
        ``signals.progress/result/error`` and ``kwargs``). Callers that need
        MC-style sync fallback pass ``sync_fn`` (the synchronous save call).
        """
        final_path_for_display = self._build_display_path(options)
        save_task_id, cancel_event = self._create_save_toast(final_path_for_display)

        # Build worker — factory may need more than cancel_event; wrap in closure at call site.
        try:
            worker = worker_factory(cancel_event)
        except Exception as exc:
            logger.error("Failed to create save worker: %s", exc, exc_info=True)
            self._on_save_worker_error(save_task_id, cancel_event, final_path_for_display, (type(exc), exc, exc.__traceback__))
            return

        # Allow factory to have already stashed progress_callback; otherwise do it here.
        try:
            worker.kwargs["progress_callback"] = worker.signals.progress
        except Exception:
            pass
        self._save_workers[save_task_id] = worker
        try:
            worker.signals.progress.connect(
                lambda value: self._on_save_worker_progress(save_task_id, final_path_for_display, value)
            )
            worker.signals.result.connect(
                lambda out_path: self._on_save_worker_done(save_task_id, cancel_event, out_path)
            )
            worker.signals.error.connect(
                lambda err_tuple: self._on_save_worker_error(save_task_id, cancel_event, final_path_for_display, err_tuple)
            )
        except Exception as exc:
            logger.error("Failed to connect worker signals: %s", exc, exc_info=True)
            self._finalize_save_worker(save_task_id)
            return

        thread_pool = self._get_thread_pool()
        if thread_pool is None:
            if self.sync_fallback and sync_fn is not None:
                logger.warning("No thread_pool available, saving synchronously on GUI thread")
                self._finalize_save_worker(save_task_id)
                try:
                    sync_fn()
                except Exception as exc:
                    logger.error("Synchronous save failed: %s", exc, exc_info=True)
                    # ensure error toast even without worker error signal
                    self._update_toast_safe(
                        save_task_id,
                        f"{self._tr('msg.error_saving', 'Error saving')} {final_path_for_display}",
                        success=False,
                        duration=5000,
                    )
                return
            logger.error("No thread_pool available and sync_fallback disabled; save aborted")
            self._update_toast_safe(
                save_task_id,
                f"{self._tr('msg.error_saving', 'Error saving')} {final_path_for_display}",
                success=False,
                duration=5000,
            )
            self._finalize_save_worker(save_task_id)
            return
        try:
            thread_pool.start(worker)
        except Exception as exc:
            logger.error("Failed to start save worker: %s", exc, exc_info=True)
            self._on_save_worker_error(save_task_id, cancel_event, final_path_for_display, (type(exc), exc, exc.__traceback__))
