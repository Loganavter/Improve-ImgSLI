from __future__ import annotations

import logging
import os
import threading

from shared.image_processing.pil_save import SAVE_CANCELED_MESSAGE

from tabs.host_helpers import MessageKind
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_compare.services import document_store_ops
from tabs._shared.save_flow import SaveFlowCoordinator as SharedSaveFlowCoordinator

logger = logging.getLogger("ImproveImgSLI")


class ExportSaveFlowCoordinator:
    """IC save-flow — thin owner delegating lifecycle to shared coordinator."""

    def __init__(
        self,
        store,
        main_window_app,
        ui_manager,
        tr_func,
        state_coordinator,
        export_service,
    ):
        self.store = store
        self.main_window_app = main_window_app
        self.ui_manager = ui_manager
        self.tr = tr_func
        self.state = state_coordinator
        self.export_service = export_service
        self._flow = SharedSaveFlowCoordinator(
            get_thread_pool=lambda: getattr(self.main_window_app, "thread_pool", None),
            get_toast_manager=lambda: getattr(self.main_window_app, "toast_manager", None),
            tr_func=tr_func,
            display_path_style="paren",
            sync_fallback=False,
            on_success_notify=self._on_success_notify,
        )

    # -- shared state exposed for tests / external callers that poke dicts --------
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

    # keep save_toast helpers accessible (tests may reach them)
    def _get_toast_manager(self):
        return self._flow._get_toast_manager()

    def _update_toast_safe(self, *args, **kwargs):
        return self._flow._update_toast_safe(*args, **kwargs)

    def _build_toast_path_line(self, *args, **kwargs):
        return self._flow._build_toast_path_line(*args, **kwargs)

    def _build_display_path(self, *args, **kwargs):
        return self._flow._build_display_path(*args, **kwargs)

    def _next_save_task_id(self):
        return self._flow._next_save_task_id()

    def _create_save_toast(self, *args, **kwargs):
        return self._flow._create_save_toast(*args, **kwargs)

    def _on_save_worker_progress(self, *args, **kwargs):
        return self._flow._on_save_worker_progress(*args, **kwargs)

    def _on_save_worker_done(self, *args, **kwargs):
        return self._flow._on_save_worker_done(*args, **kwargs)

    def _on_save_worker_error(self, *args, **kwargs):
        return self._flow._on_save_worker_error(*args, **kwargs)

    def _finalize_save_worker(self, *args, **kwargs):
        return self._flow._finalize_save_worker(*args, **kwargs)

    def cancel_all_exports(self):
        return self._flow.cancel_all_exports()

    # -- IC-specific ------------------------------------------------------------
    def _on_success_notify(self, out_path: str) -> None:
        try:
            self.main_window_app.actions.set_last_saved_path(out_path)
            self.main_window_app.actions.update_tray_actions_visibility()
            notifications_enabled = getattr(
                self.store.settings,
                "system_notifications_enabled",
                True,
            )
            if notifications_enabled:
                image_for_icon = (
                    out_path if isinstance(out_path, str) and os.path.isfile(out_path) else None
                )
                self.main_window_app.actions.notify_system(
                    self.tr("msg.saved"),
                    f"{self.tr('msg.saved')}: {out_path}",
                    image_path=image_for_icon,
                    timeout_ms=4000,
                )
        except Exception as exc:
            logger.error("Save notification failed: %s", exc, exc_info=True)

    def validate_export_options(self, export_opts: dict) -> bool:
        out_dir = export_opts.get("output_dir")
        out_name = export_opts.get("file_name")
        if out_dir and out_name:
            return True
        self.ui_manager.messages.show_non_modal_message(
            kind=MessageKind.WARNING,
            title=self.tr("image_compare.msg.invalid_data"),
            text=self.tr("image_compare.msg.specify_output_directory_and_file_name"),
        )
        return False

    def show_missing_images_warning(self) -> None:
        self.ui_manager.messages.show_non_modal_message(
            kind=MessageKind.WARNING,
            title=self.tr("image_compare.common.warning"),
            text=self.tr("image_compare.msg.select_both_images_first"),
        )

    def start_save_worker(
        self,
        save_ctx,
        export_opts: dict,
    ) -> None:
        def worker_factory(cancel_event: threading.Event):
            return GenericWorker(
                self._export_worker_task,
                store_copy=document_store_ops.copy_for_worker(self.store),
                image1_for_save=save_ctx.image1_for_save,
                image2_for_save=save_ctx.image2_for_save,
                original1_full=save_ctx.original1_full,
                original2_full=save_ctx.original2_full,
                render_plan=save_ctx.render_plan,
                render_store=save_ctx.render_store,
                export_options=export_opts,
                cancel_event=cancel_event,
                file_name1_text=self.state.get_current_display_name(1),
                file_name2_text=self.state.get_current_display_name(2),
            )

        self._flow.start_with_worker(export_opts, worker_factory)

    def _export_worker_task(self, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        cancel_event = kwargs.get("cancel_event")
        store_copy = kwargs["store_copy"]
        original1_full = kwargs["original1_full"]
        original2_full = kwargs["original2_full"]
        export_options = kwargs["export_options"]
        render_plan = kwargs.get("render_plan")
        render_store = kwargs.get("render_store")

        def emit_progress(val):
            if progress_callback:
                progress_callback.emit(val)

        try:
            return self.export_service.export_image(
                store=store_copy,
                original_image1=original1_full,
                original_image2=original2_full,
                export_options=export_options,
                render_plan=render_plan,
                render_store=render_store,
                cancel_event=cancel_event,
                progress_callback=lambda v: emit_progress(v),
            )
        except RuntimeError as e:
            if str(e) in ("Export canceled by user", SAVE_CANCELED_MESSAGE):
                return None
            raise
        except Exception as e:
            logger.error(f"Export worker task failed: {e}", exc_info=True)
            raise e
