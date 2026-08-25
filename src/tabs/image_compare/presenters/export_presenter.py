import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog

from tabs.host_helpers import MessageKind

from core.store import Store
from plugins.export.services.gpu_export import GpuExportService
from sli_ui_toolkit.i18n import tr

logger = logging.getLogger("ImproveImgSLI")

class ExportPresenter(QObject):
    """Still-image export glue for image_compare.

    Built as a tab-owned service (``TabRegistry.create_startup_service``,
    see ``tabs/image_compare/service_factory.py``'s ``"export_presenter"``
    id) rather than imported directly by the host composer — still-image
    export is entirely image_compare's own concept (its own context
    builder, save-flow, dialog trigger); nothing here is shared with other
    tabs, unlike a true host capability.
    """

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

        from tabs.image_compare.services.image_export import ExportService
        from tabs.image_compare.services.image_export.context_builder import (
            ExportContextBuilder,
        )
        from tabs.image_compare.services.image_export.save_flow import (
            ExportSaveFlowCoordinator,
        )
        from tabs.image_compare.services.export_state import ExportStateCoordinator

        self.gpu_export_service = GpuExportService(
            parent=main_window_app,
            resource_manager=resource_manager,
        )
        self.export_service = ExportService(
            font_path_absolute=font_path_absolute,
            gpu_export_service=self.gpu_export_service,
        )
        self.state = ExportStateCoordinator(
            store=store,
            main_controller=main_controller,
            main_window_app=main_window_app,
        )
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
            export_service=self.export_service,
        )

    def _tr(self, text):
        return tr(text, self.store.settings.current_language)

    def _tr_export(self, key: str, default: str | None = None) -> str:
        text = self._tr(key)
        if not text or text == key:
            return default or key
        return text

    def _untested_export_suppressed(self) -> bool:
        from shared.export_warning_state import is_untested_export_suppressed

        return is_untested_export_suppressed(getattr(self.store, "settings", None))

    def _suppress_untested_export_warning(self) -> None:
        from shared.export_warning_state import set_untested_export_suppressed

        set_untested_export_suppressed(
            getattr(self.store, "settings", None),
            getattr(self.main_controller, "settings_manager", None),
            True,
        )

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
                kind=MessageKind.WARNING,
                title=self._tr("image_compare.common.warning"),
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
                kind=MessageKind.CRITICAL,
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
                save_ctx.preview_img,
                save_ctx.suggested_filename,
                native_size=(save_ctx.native_width, save_ctx.native_height),
                virtual_canvas_active=bool(save_ctx.virtual_canvas_active),
            )
            if int(result_code) != int(QDialog.DialogCode.Accepted):
                return

            if not self.save_flow.validate_export_options(export_opts):
                return

            from shared.untested_export_resolution import (
                confirm_untested_export_resolution,
            )

            if not confirm_untested_export_resolution(
                self.main_window_app,
                int(export_opts.get("width") or 0),
                int(export_opts.get("height") or 0),
                translate=self._tr_export,
                suppressed=self._untested_export_suppressed(),
                on_suppress=self._suppress_untested_export_warning,
            ):
                return

            self.save_flow.start_save_worker(
                save_ctx=save_ctx,
                export_opts=export_opts,
            )
            self.state.persist_export_settings(export_opts)

        except Exception as e:
            logger.error(f"Error during save preparation: {e}", exc_info=True)
            self.ui_manager.messages.show_non_modal_message(
                kind=MessageKind.CRITICAL,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_save_image')}: {str(e)}",
            )

    def _open_export_dialog(
        self,
        preview_img,
        suggested_filename: str,
        native_size=None,
        *,
        virtual_canvas_active: bool = True,
    ):
        dialog_state = self.state.build_export_dialog_state()
        dialog_state.virtual_canvas_active = bool(virtual_canvas_active)
        return self.ui_manager.dialogs.show_export_dialog(
            dialog_state=dialog_state,
            preview_image=preview_img,
            suggested_filename=suggested_filename,
            on_set_favorite_dir=self._set_export_favorite_dir,
            native_size=native_size,
        )

    def open_snapshot_export_dialog(
        self,
        *,
        preview_image,
        suggested_filename: str,
        native_size: tuple[int, int],
    ):
        """Open the standard image-export dialog for a host-provided snapshot."""
        return self._open_export_dialog(
            preview_image,
            suggested_filename,
            native_size=native_size,
        )

    def quick_save(self):
        if not self.context_builder.has_images():
            self.save_flow.show_missing_images_warning()
            return

        try:
            save_ctx = self.context_builder.build_save_context(include_preview=False)
            export_opts = self.state.build_quick_export_options()
            if not save_ctx.virtual_canvas_active:
                export_opts["fill_background"] = False
            from shared.untested_export_resolution import (
                confirm_untested_export_resolution,
            )

            if not confirm_untested_export_resolution(
                self.main_window_app,
                int(export_opts.get("width") or 0),
                int(export_opts.get("height") or 0),
                translate=self._tr_export,
                suppressed=self._untested_export_suppressed(),
                on_suppress=self._suppress_untested_export_warning,
            ):
                return

            self.save_flow.start_save_worker(
                save_ctx=save_ctx,
                export_opts=export_opts,
            )

        except Exception as e:
            logger.error(f"Error during quick save preparation: {e}", exc_info=True)
            self.ui_manager.messages.show_non_modal_message(
                kind=MessageKind.CRITICAL,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_quick_save_image')}: {str(e)}",
            )

    def cancel_all_exports(self):
        self.save_flow.cancel_all_exports()
