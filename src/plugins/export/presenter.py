
import logging
import os
import re
import threading
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QDialog
import PIL.Image

from core.store import Store
from shared.image_processing.pipeline import RenderingPipeline, create_render_context_from_store
from shared.image_processing.resize import resize_images_processor
from plugins.export.services.image_export import ExportService
from shared_toolkit.workers import GenericWorker
from utils.resource_loader import get_magnifier_drawing_coords
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
        parent=None
    ):
        super().__init__(parent)
        self.store = store
        self.main_controller = main_controller
        self.ui_manager = ui_manager
        self.main_window_app = main_window_app
        self.font_path_absolute = font_path_absolute

        self.export_service = ExportService(font_path_absolute)

        self._save_cancellation = {}
        self._save_workers = {}
        self._file_dialog = None
        self._first_dialog_load_pending = True

    def _tr(self, text):
        return tr(text, self.store.settings.current_language)

    def _get_os_default_downloads(self):

        if hasattr(self.main_window_app, '_get_os_default_downloads'):
            return self.main_window_app._get_os_default_downloads()

        from pathlib import Path
        return str(Path.home() / "Downloads")

    def _get_unique_filepath(self, directory: str, base_name: str, extension: str) -> str:
        full_path = os.path.join(directory, f"{base_name}{extension}")
        if not os.path.exists(full_path):
            return full_path

        counter = 1
        while True:
            new_name = f"{base_name} ({counter})"
            new_path = os.path.join(directory, f"{new_name}{extension}")
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def _qcolor_from_tuple(self, color_tuple):
        if color_tuple is None:
            return QColor(255, 255, 255, 255)
        return QColor(*color_tuple)

    def _default_bg_color(self):
        return QColor(255, 255, 255, 255)

    def save_result(self):
        if not self.store.document.original_image1 or not self.store.document.original_image2:
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=self._tr("common.warning"),
                text=self._tr("msg.please_load_and_select_images_in_both_slots_first")
            )
            return

        try:
            original1_full = self.store.document.full_res_image1 or self.store.document.original_image1
            original2_full = self.store.document.full_res_image2 or self.store.document.original_image2

            if not original1_full or not original2_full:
                raise ValueError("Full resolution images are not available for saving.")

            image1_for_save, image2_for_save = resize_images_processor(
                original1_full, original2_full
            )
            if not image1_for_save or not image2_for_save:
                raise ValueError("Failed to unify images for saving.")

            save_width, save_height = image1_for_save.size

            magnifier_coords_for_save = get_magnifier_drawing_coords(
                store=self.store,
                drawing_width=save_width,
                drawing_height=save_height,
                container_width=save_width,
                container_height=save_height,
            ) if self.store.viewport.use_magnifier else None

            preview_scale = max(1, min(5, max(save_width, save_height) // 800))
            preview_w = max(1, save_width // preview_scale)
            preview_h = max(1, save_height // preview_scale)

            magnifier_coords_for_preview = get_magnifier_drawing_coords(
                store=self.store,
                drawing_width=preview_w,
                drawing_height=preview_h,
            ) if self.store.viewport.use_magnifier else None

            image1_preview = image1_for_save.resize(
                (preview_w, preview_h), PIL.Image.Resampling.BILINEAR
            )
            image2_preview = image2_for_save.resize(
                (preview_w, preview_h), PIL.Image.Resampling.BILINEAR
            )

            ctx = create_render_context_from_store(
                store=self.store,
                width=preview_w,
                height=preview_h,
                magnifier_drawing_coords=magnifier_coords_for_preview,
                image1_scaled=image1_preview,
                image2_scaled=image2_preview
            )
            ctx.file_name1 = self._get_current_display_name(1)
            ctx.file_name2 = self._get_current_display_name(2)

            pipeline = RenderingPipeline(self.font_path_absolute)
            preview_img, _, _, _, _, _ = pipeline.render_frame(ctx)
            if preview_img is None:
                preview_img = PIL.Image.new(
                    "RGBA", (preview_w, preview_h), (200, 200, 200, 255)
                )

            name1 = (self._get_current_display_name(1) or "image1").strip()
            name2 = (self._get_current_display_name(2) or "image2").strip()

            def sanitize(s: str) -> str:
                s = re.sub(r'[\\/*?:"<>|]', "_", s)
                return s[:80]

            base_name = f"{sanitize(name1)}_{sanitize(name2)}"
            out_dir = self.store.settings.export_default_dir or self._get_os_default_downloads()
            fmt = (self.store.settings.export_last_format or "PNG").upper()
            ext = "." + fmt.lower().replace("jpeg", "jpg")

            unique_full_path = self._get_unique_filepath(out_dir, base_name, ext)
            unique_filename_without_ext = os.path.splitext(
                os.path.basename(unique_full_path)
            )[0]

            result_code, export_opts = self.ui_manager.show_export_dialog(
                preview_img, suggested_filename=unique_filename_without_ext
            )
            if int(result_code) != int(QDialog.DialogCode.Accepted):
                return

            out_dir = export_opts.get("output_dir")
            out_name = export_opts.get("file_name")
            if not out_dir or not out_name:
                self.ui_manager.show_non_modal_message(
                    icon=QMessageBox.Icon.Warning,
                    title=self._tr("msg.invalid_data"),
                    text=self._tr("msg.please_specify_output_directory_and_file_name")
                )
                return

            store_copy = self.store.copy_for_worker()
            save_task_id = self.main_window_app.save_task_counter
            self.main_window_app.save_task_counter += 1

            fmt_disp = (export_opts.get("format", "PNG") or "PNG").upper()
            ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
            final_path_for_display = os.path.join(out_dir, f"{out_name}{ext_disp}")
            toast_message = (
                f"{self._tr('msg.saving')}\n{final_path_for_display}..."
            )

            cancel_event = threading.Event()
            _cancel_ctx = {"event": cancel_event}

            def on_cancel():
                ev = _cancel_ctx.get("event")
                toast_id = _cancel_ctx.get("id")
                if ev:
                    ev.set()
                if toast_id is not None:
                    self.main_window_app.toast_manager.update_toast(
                        toast_id,
                        self._tr("msg.saving_canceled"),
                        success=False,
                        duration=3000,
                    )

            save_task_id = self.main_window_app.toast_manager.show_toast(
                toast_message,
                duration=0,
                action_text=self._tr("common.cancel"),
                on_action=on_cancel,
            )
            _cancel_ctx["id"] = save_task_id
            self._save_cancellation[save_task_id] = cancel_event

            worker = GenericWorker(
                self._export_worker_task,
                store_copy=store_copy,
                image1_for_save=image1_for_save,
                image2_for_save=image2_for_save,
                original1_full=original1_full,
                original2_full=original2_full,
                magnifier_drawing_coords=magnifier_coords_for_save,
                export_options=export_opts,
                cancel_event=cancel_event,
                file_name1_text=self._get_current_display_name(1),
                file_name2_text=self._get_current_display_name(2),
            )
            self._save_workers[save_task_id] = worker

            def _on_done(out_path):
                if cancel_event.is_set():
                    return
                success_message = f"{self._tr('msg.saved')} {os.path.basename(out_path)}"
                self.main_window_app.toast_manager.update_toast(
                    save_task_id, success_message, success=True
                )
                try:
                    setattr(self.main_window_app, "_last_saved_path", out_path)
                    if hasattr(self.main_window_app, "update_tray_actions_visibility"):
                        self.main_window_app.update_tray_actions_visibility()
                    tray = getattr(self.main_window_app, "tray_icon", None)
                    if getattr(self.store.settings, "system_notifications_enabled", True):
                        image_for_icon = (
                            out_path
                            if isinstance(out_path, str) and os.path.isfile(out_path)
                            else None
                        )
                        self.main_window_app.notify_system(
                            self._tr("msg.saved"),
                            f"{self._tr('msg.saved')}: {out_path}",
                            image_path=image_for_icon,
                            timeout_ms=4000,
                        )
                except Exception as e:
                    logger.error(f"Tray notification error: {e}")
                finally:
                    self._save_cancellation.pop(save_task_id, None)
                    self._save_workers.pop(save_task_id, None)

            def _on_err(err_tuple):
                if not cancel_event.is_set():
                    error_message = f"{self._tr('msg.error_saving')} {final_path_for_display}"
                    self.main_window_app.toast_manager.update_toast(
                        save_task_id, error_message, success=False, duration=8000
                    )
                self._save_cancellation.pop(save_task_id, None)
                self._save_workers.pop(save_task_id, None)

            worker.signals.result.connect(_on_done)
            worker.signals.error.connect(_on_err)
            self.main_window_app.thread_pool.start(worker)

            self.store.settings.export_last_format = export_opts.get("format", "PNG")
            self.store.settings.export_quality = int(export_opts.get("quality", 95))
            self.store.settings.export_fill_background = bool(
                export_opts.get("fill_background", False)
            )
            bg_c = export_opts.get("background_color")
            self.store.settings.export_background_color = (
                self._qcolor_from_tuple(bg_c) if bg_c else self._default_bg_color()
            )
            self.store.settings.export_last_filename = out_name
            self.store.settings.export_default_dir = out_dir
            self.store.settings.export_png_compress_level = int(
                export_opts.get("png_compress_level", 9)
            )

            if bool(export_opts.get("comment_keep_default", False)):
                self.store.settings.export_comment_text = export_opts.get("comment_text", "")
                self.store.settings.export_comment_keep_default = True
            else:
                self.store.settings.export_comment_text = ""
                self.store.settings.export_comment_keep_default = False

            if self.main_controller and hasattr(self.main_controller, 'settings_manager'):
                self.main_controller.settings_manager.save_all_settings(self.store)

        except Exception as e:
            logger.error(f"Error during save preparation: {e}", exc_info=True)
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_save_image')}: {str(e)}",
            )

    def quick_save(self):
        if not self.store.document.original_image1 or not self.store.document.original_image2:
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=self._tr("common.warning"),
                text=self._tr("msg.please_load_and_select_images_in_both_slots_first")
            )
            return

        if not hasattr(self.store.settings, 'export_default_dir') or not self.store.settings.export_default_dir:
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=self._tr("common.warning"),
                text=self._tr("button.no_previous_export_settings_found_please_use_save_result_first")
            )
            return

        try:
            original1_full = self.store.document.full_res_image1 or self.store.document.original_image1
            original2_full = self.store.document.full_res_image2 or self.store.document.original_image2

            if not original1_full or not original2_full:
                raise ValueError("Full resolution images are not available for saving.")

            image1_for_save, image2_for_save = resize_images_processor(
                original1_full, original2_full
            )
            if not image1_for_save or not image2_for_save:
                raise ValueError("Failed to unify images for saving.")

            save_width, save_height = image1_for_save.size

            magnifier_coords_for_save = get_magnifier_drawing_coords(
                store=self.store,
                drawing_width=save_width,
                drawing_height=save_height,
                container_width=save_width,
                container_height=save_height,
            ) if self.store.viewport.use_magnifier else None

            store_copy = self.store.copy_for_worker()

            bg_color_qcolor = getattr(
                self.store.settings, 'export_background_color',
                self._default_bg_color()
            )
            bg_color_tuple = (
                bg_color_qcolor.red(),
                bg_color_qcolor.green(),
                bg_color_qcolor.blue(),
                bg_color_qcolor.alpha(),
            )

            name1 = (self._get_current_display_name(1) or "image1").strip()
            name2 = (self._get_current_display_name(2) or "image2").strip()

            def sanitize(s: str) -> str:
                s = re.sub(r'[\\/*?:"<>|]', "_", s)
                return s[:80]

            base_name = f"{sanitize(name1)}_{sanitize(name2)}"

            export_options = {
                "output_dir": self.store.settings.export_default_dir,
                "file_name": base_name,
                "format": self.store.settings.export_last_format or "PNG",
                "quality": self.store.settings.export_quality or 95,
                "fill_background": getattr(self.store.settings, 'export_fill_background', False),
                "background_color": bg_color_tuple,
                "png_compress_level": getattr(self.store.settings, 'export_png_compress_level', 9),
                "png_optimize": True,
                "include_metadata": bool(getattr(
                    self.store.settings, 'export_comment_keep_default', False
                )),
                "comment_text": (
                    getattr(self.store.settings, 'export_comment_text', '')
                    if getattr(self.store.settings, 'export_comment_keep_default', False)
                    else ''
                ),
                "is_quick_save": True,
            }

            save_task_id = self.main_window_app.save_task_counter
            self.main_window_app.save_task_counter += 1

            fmt_disp = (export_options.get("format", "PNG") or "PNG").upper()
            ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
            display_path = os.path.join(
                export_options.get("output_dir"),
                f"{export_options.get('file_name')}{ext_disp}"
            )
            toast_message = f"{self._tr('msg.saving')}\n{display_path}..."

            cancel_event = threading.Event()
            _cancel_ctx = {"event": cancel_event}

            def on_cancel_quick():
                ev = _cancel_ctx.get("event")
                toast_id = _cancel_ctx.get("id")
                if ev:
                    ev.set()
                if toast_id is not None:
                    self.main_window_app.toast_manager.update_toast(
                        toast_id,
                        self._tr("msg.saving_canceled"),
                        success=False,
                        duration=3000,
                    )

            save_task_id = self.main_window_app.toast_manager.show_toast(
                toast_message,
                duration=0,
                action_text=self._tr("common.cancel"),
                on_action=on_cancel_quick,
            )
            _cancel_ctx["id"] = save_task_id
            self._save_cancellation[save_task_id] = cancel_event

            worker = GenericWorker(
                self._export_worker_task,
                store_copy=store_copy,
                image1_for_save=image1_for_save,
                image2_for_save=image2_for_save,
                original1_full=original1_full,
                original2_full=original2_full,
                magnifier_drawing_coords=magnifier_coords_for_save,
                export_options=export_options,
                cancel_event=cancel_event,
                file_name1_text=self._get_current_display_name(1),
                file_name2_text=self._get_current_display_name(2),
            )
            self._save_workers[save_task_id] = worker

            def _on_done_quick(out_path):
                if cancel_event.is_set():
                    return
                success_message = f"{self._tr('msg.saved')} {os.path.basename(out_path)}"
                self.main_window_app.toast_manager.update_toast(
                    save_task_id, success_message, success=True
                )
                try:
                    setattr(self.main_window_app, "_last_saved_path", out_path)
                    if hasattr(self.main_window_app, "update_tray_actions_visibility"):
                        self.main_window_app.update_tray_actions_visibility()

                    if getattr(self.store.settings, "system_notifications_enabled", True):
                        image_for_icon = (
                            out_path
                            if isinstance(out_path, str) and os.path.isfile(out_path)
                            else None
                        )
                        self.main_window_app.notify_system(
                            self._tr("msg.saved"),
                            f"{self._tr('msg.saved')}: {out_path}",
                            image_path=image_for_icon,
                            timeout_ms=4000,
                        )
                except Exception as e:
                    logger.error(f"Tray notification error in quick save: {e}")
                finally:
                    self._save_cancellation.pop(save_task_id, None)
                    self._save_workers.pop(save_task_id, None)

            def _on_err_quick(err_tuple):
                if not cancel_event.is_set():
                    error_message = f"{self._tr('msg.error_saving')} {display_path}"
                    self.main_window_app.toast_manager.update_toast(
                        save_task_id, error_message, success=False, duration=8000
                    )
                self._save_cancellation.pop(save_task_id, None)
                self._save_workers.pop(save_task_id, None)

            worker.signals.result.connect(_on_done_quick)
            worker.signals.error.connect(_on_err_quick)
            self.main_window_app.thread_pool.start(worker)

        except Exception as e:
            logger.error(f"Error during quick save preparation: {e}", exc_info=True)
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=self._tr("common.error"),
                text=f"{self._tr('msg.failed_to_quick_save_image')}: {str(e)}",
            )

    def _export_worker_task(self, **kwargs):
        progress_callback = kwargs.get('progress_callback')
        cancel_event = kwargs.get('cancel_event')
        store_copy = kwargs['store_copy']
        original1_full = kwargs['original1_full']
        original2_full = kwargs['original2_full']
        export_options = kwargs['export_options']

        def emit_progress(val):
            if progress_callback:
                progress_callback.emit(val)

        try:

            result = self.export_service.export_image(
                store=store_copy,
                original_image1=original1_full,
                original_image2=original2_full,
                export_options=export_options,
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
        logger.debug(f"Отмена всех активных экспортов (всего: {len(self._save_cancellation)})")

        for save_task_id, cancel_event in list(self._save_cancellation.items()):
            if cancel_event:
                cancel_event.set()
                logger.info(f"Экспорт {save_task_id} отменен")

        for save_task_id in list(self._save_cancellation.keys()):
            if hasattr(self.main_window_app, 'toast_manager'):
                try:
                    self.main_window_app.toast_manager.update_toast(
                        save_task_id,
                        self._tr("msg.saving_canceled"),
                        success=False,
                        duration=2000,
                    )
                except Exception as e:
                    logger.error(f"Ошибка при обновлении тоста {save_task_id}: {e}")

        self._save_cancellation.clear()
        self._save_workers.clear()

        logger.debug("Все активные экспорты отменены")

    def _get_current_display_name(self, image_number: int) -> str:
        target_list, index = (
            (self.store.document.image_list1, self.store.document.current_index1)
            if image_number == 1
            else (self.store.document.image_list2, self.store.document.current_index2)
        )
        if 0 <= index < len(target_list):
            return target_list[index].display_name
        return ""

