import logging

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QDialog, QMessageBox

from core.store import Store
from plugins.export.presenter_parts import (
    ExportContextBuilder,
    ExportSaveFlowCoordinator,
    ExportStateCoordinator,
)
from plugins.export.services.gpu_export import GpuExportService
from plugins.export.services.image_export import ExportService
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

class ExportPresenter(QObject):

    def __init__(
        self,
        store: Store,
        main_controller,
        ui_manager,
        main_window_app,
        font_path_absolute,
        resource_manager=None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui_manager = ui_manager
        self.main_window_app = main_window_app
        self.font_path_absolute = font_path_absolute

        self.gpu_export_service = GpuExportService(
            parent=main_window_app,
            resource_manager=resource_manager,
        )
        self.export_service = ExportService(
            font_path_absolute, gpu_export_service=self.gpu_export_service
        )
        self.state = ExportStateCoordinator(store, main_controller, main_window_app)
        self.context_builder = ExportContextBuilder(
            store=store,
            gpu_export_service=self.gpu_export_service,
            state_coordinator=self.state,
        )
        self.save_flow = ExportSaveFlowCoordinator(
            store=store,
            main_window_app=main_window_app,
            ui_manager=ui_manager,
            tr_func=self._tr,
            state_coordinator=self.state,
        )

    def _tr(self, text):
        return tr(text, self.store.settings.current_language)

    def shutdown(self) -> None:
        try:
            self.cancel_all_exports()
        except Exception:
            logger.exception("Failed to cancel exports during shutdown")
        try:
            self.gpu_export_service.shutdown()
        except Exception:
            logger.exception("Failed to shutdown GPU export service")

    def sync_recording_controls(
        self, is_recording: bool, is_paused: bool = False, pause_enabled: bool = False
    ):
        ui = getattr(self.main_window_app, "ui", None)
        if ui is None:
            return

        if hasattr(ui, "btn_record"):
            ui.btn_record.blockSignals(True)
            ui.btn_record.setChecked(is_recording)
            ui.btn_record.blockSignals(False)

        if hasattr(ui, "btn_pause"):
            ui.btn_pause.setEnabled(pause_enabled)
            ui.btn_pause.setChecked(is_paused)

    def open_video_editor(self, snapshots, export_controller, video_editor_plugin):
        if not snapshots or export_controller is None or video_editor_plugin is None:
            self.ui_manager.messages.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=self._tr("common.warning"),
                text="Video editor is unavailable.",
            )
            return

        try:
            video_editor_plugin.open_editor(
                snapshots, export_controller, self.main_window_app
            )
        except Exception as exc:
            logger.exception("Failed to open video editor: %s", exc)
            self.ui_manager.messages.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=self._tr("common.error"),
                text=f"Failed to open video editor: {exc}",
            )

    def _set_export_favorite_dir(self, path: str) -> None:
        self.state.set_export_favorite_dir(path)

    def save_result(self):
        if not self.context_builder.has_images():
            self.save_flow.show_missing_images_warning()
            return

        try:
            save_ctx = self.context_builder.build_save_context(include_preview=True)
            result_code, export_opts = self._open_export_dialog(
                save_ctx.preview_img, save_ctx.suggested_filename
            )
            if int(result_code) != int(QDialog.DialogCode.Accepted):
                return

            if not self.save_flow.validate_export_options(export_opts):
                return

            self.save_flow.start_save_worker(
                save_ctx=save_ctx,
                export_opts=export_opts,
                export_runner=self._export_worker_task,
            )
            self.state.persist_export_settings(export_opts)

        except Exception as e:
            logger.error(f"Error during save preparation: {e}", exc_info=True)
            self.ui_manager.messages.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_save_image')}: {str(e)}",
            )

    def _open_export_dialog(self, preview_img, suggested_filename: str):
        return self.ui_manager.dialogs.show_export_dialog(
            dialog_state=self.state.build_export_dialog_state(),
            preview_image=preview_img,
            suggested_filename=suggested_filename,
            on_set_favorite_dir=self._set_export_favorite_dir,
        )

    def quick_save(self):
        if not self.context_builder.has_images():
            self.save_flow.show_missing_images_warning()
            return

        try:
            save_ctx = self.context_builder.build_save_context(include_preview=False)
            self.save_flow.start_save_worker(
                save_ctx=save_ctx,
                export_opts=self.state.build_quick_export_options(),
                export_runner=self._export_worker_task,
            )

        except Exception as e:
            logger.error(f"Error during quick save preparation: {e}", exc_info=True)
            self.ui_manager.messages.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_quick_save_image')}: {str(e)}",
            )

    def _export_worker_task(self, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        cancel_event = kwargs.get("cancel_event")
        store_copy = kwargs["store_copy"]
        original1_full = kwargs["original1_full"]
        original2_full = kwargs["original2_full"]
        export_options = kwargs["export_options"]
        render_context = kwargs.get("render_context")

        def emit_progress(val):
            if progress_callback:
                progress_callback.emit(val)

        try:

            result = self.export_service.export_image(
                store=store_copy,
                original_image1=original1_full,
                original_image2=original2_full,
                export_options=export_options,
                render_context=render_context,
                cancel_event=cancel_event,
                progress_callback=lambda v: emit_progress(v),
            )
            return result
        except RuntimeError as e:
            if str(e) == "Export canceled by user":
                return None
            raise
        except Exception as e:
            logger.error(f"Export worker task failed: {e}", exc_info=True)
            raise e

    def cancel_all_exports(self):
        self.save_flow.cancel_all_exports()
