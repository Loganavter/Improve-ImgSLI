"""Background save-flow coordinator for the Multi Compare tab — delegates to shared."""

from __future__ import annotations

import logging
import threading

from PIL import Image
from sli_ui_toolkit.workers import GenericWorker

from shared.image_processing.pil_save import SAVE_CANCELED_MESSAGE

from tabs.multi_compare.services.image_export import save_composite
from tabs._shared.save_flow import SaveFlowCoordinator as SharedSaveFlowCoordinator

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareSaveFlowCoordinator:
    """MC save-flow — thin owner delegating lifecycle to shared coordinator."""

    def __init__(self, main_window_app, tr_func, thread_pool=None):
        self.main_window_app = main_window_app
        self.tr = tr_func
        self._thread_pool = thread_pool
        self._flow = SharedSaveFlowCoordinator(
            get_thread_pool=lambda: self._thread_pool or getattr(self.main_window_app, "thread_pool", None),
            get_toast_manager=lambda: getattr(self.main_window_app, "toast_manager", None),
            tr_func=tr_func,
            display_path_style="underscore",
            sync_fallback=True,
        )

    @property
    def _save_cancellation(self):
        return self._flow._save_cancellation

    @_save_cancellation.setter
    def _save_cancellation(self, value):
        self._flow._save_cancellation = value

    @property
    def _save_workers(self):
        return self._flow._save_workers

    @_save_workers.setter
    def _save_workers(self, value):
        self._flow._save_workers = value

    def _get_thread_pool(self):
        return self._flow._get_thread_pool()

    def _get_toast_manager(self):
        return self._flow._get_toast_manager()

    def _update_toast_safe(self, *a, **kw):
        return self._flow._update_toast_safe(*a, **kw)

    def _build_toast_path_line(self, *a, **kw):
        return self._flow._build_toast_path_line(*a, **kw)

    def _build_display_path(self, *a, **kw):
        return self._flow._build_display_path(*a, **kw)

    def _next_save_task_id(self):
        return self._flow._next_save_task_id()

    def _create_save_toast(self, *a, **kw):
        return self._flow._create_save_toast(*a, **kw)

    def _on_save_worker_progress(self, *a, **kw):
        return self._flow._on_save_worker_progress(*a, **kw)

    def _on_save_worker_done(self, *a, **kw):
        return self._flow._on_save_worker_done(*a, **kw)

    def _on_save_worker_error(self, *a, **kw):
        return self._flow._on_save_worker_error(*a, **kw)

    def _finalize_save_worker(self, *a, **kw):
        return self._flow._finalize_save_worker(*a, **kw)

    def cancel_all_exports(self):
        return self._flow.cancel_all_exports()

    def start_save_worker(self, pil_image: Image.Image, options: dict) -> None:
        """``pil_image`` must already be a plain ``PIL.Image`` (converted on the GUI thread)."""

        def worker_factory(cancel_event: threading.Event):
            return GenericWorker(
                self._save_worker_task,
                pil_image=pil_image,
                options=options,
                cancel_event=cancel_event,
            )

        def sync_fn():
            return save_composite(pil_image, options)

        self._flow.start_with_worker(options, worker_factory, sync_fn=sync_fn)

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
            if str(e) in (SAVE_CANCELED_MESSAGE, "Export canceled by user"):
                return None
            raise
        except Exception as e:
            logger.error("[mc-save] worker task failed: %s", e, exc_info=True)
            raise
