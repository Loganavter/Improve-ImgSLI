import logging
import os
import re
import threading

import PIL.Image
from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QWidget,
)

from core.app_state import AppState
from core.constants import AppConstants
from core.main_controller import MainController
from events.image_label_event_handler import ImageLabelEventHandler
from events.window_event_handler import WindowEventHandler
from image_processing.composer import ImageComposer
from image_processing.resize import resize_images_processor
from resources import translations as translations_mod
from ui.icon_manager import AppIcon, get_app_icon
from ui.main_window_ui import Ui_ImageComparisonApp
from ui.managers.ui_manager import UIManager
from ui.presenters.ui_update_batcher import UIUpdateBatcher
from utils.resource_loader import get_magnifier_drawing_coords
from shared_toolkit.workers import GenericWorker

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)
logger = logging.getLogger("ImproveImgSLI")

class MainWindowPresenter(QObject):
    def __init__(self, main_window_app: QWidget, ui: Ui_ImageComparisonApp, app_state: AppState, main_controller: MainController):
        super().__init__(main_window_app)
        self.main_window_app = main_window_app
        self.ui = ui
        self.app_state = app_state
        self.main_controller = main_controller

        self.image_label_handler = ImageLabelEventHandler(app_state, main_controller, self)
        self.window_handler = WindowEventHandler(app_state, main_controller, ui, main_window_app)
        self.ui_manager = UIManager(app_state, main_controller, ui, main_window_app)

        self.ui_batcher = UIUpdateBatcher(self)

        self._divider_color_dialog = None
        self._magnifier_divider_color_dialog = None

        from ui.widgets.composite.text_settings_flyout import FontSettingsFlyout
        self.font_settings_flyout = FontSettingsFlyout(main_window_app)
        self.font_settings_flyout.hide()
        self.ui_manager.font_settings_flyout = self.font_settings_flyout

        self._orientation_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(self._hide_orientation_popup)

        self._connect_signals()

        self._save_cancellation = {}
        self._save_workers = {}
        self._file_dialog = None
        self._first_dialog_load_pending = True

        try:
            self._apply_initial_settings_to_ui()
            self.ui.update_translations(self.app_state.current_language)
            self.update_slider_tooltips()
            self.ui.reapply_button_styles()
            self.repopulate_flyouts()
        except Exception:
            pass

    def _connect_signals(self):
        self.ui.btn_swap.shortClicked.connect(self.main_controller.swap_current_images)
        self.ui.btn_swap.longPressed.connect(self.main_controller.swap_entire_lists)
        self.ui.btn_clear_list1.shortClicked.connect(lambda: self.main_controller.remove_current_image_from_list(1))
        self.ui.btn_clear_list1.longPressed.connect(lambda: self.main_controller.clear_image_list(1))
        self.ui.btn_clear_list2.shortClicked.connect(lambda: self.main_controller.remove_current_image_from_list(2))
        self.ui.btn_clear_list2.longPressed.connect(lambda: self.main_controller.clear_image_list(2))

        self.ui.edit_name1.editingFinished.connect(lambda: self.main_controller.on_edit_name_changed(1, self.ui.edit_name1.text()))
        self.ui.edit_name2.editingFinished.connect(lambda: self.main_controller.on_edit_name_changed(2, self.ui.edit_name2.text()))
        self.ui.edit_name1.textChanged.connect(self.check_name_lengths)
        self.ui.edit_name2.textChanged.connect(self.check_name_lengths)

        self.ui.edit_name1.textEdited.connect(lambda text: self.main_controller.on_edit_name_changed(1, text))
        self.ui.edit_name2.textEdited.connect(lambda text: self.main_controller.on_edit_name_changed(2, text))

        self.ui.btn_orientation.toggled.connect(self.main_controller.toggle_orientation)
        self.ui.btn_orientation.rightClicked.connect(self._toggle_magnifier_orientation_on_right_click)
        self.ui.btn_magnifier_orientation.toggled.connect(self.main_controller.toggle_magnifier_orientation)
        self.ui.btn_magnifier_orientation.rightClicked.connect(self.ui.btn_magnifier_orientation.click)
        self.ui.btn_magnifier.toggled.connect(self.main_controller.toggle_magnifier)
        self.ui.btn_file_names.toggled.connect(self.main_controller.toggle_include_filenames_in_saved)
        self.ui.btn_freeze.toggled.connect(self.main_controller.toggle_freeze_magnifier)

        self.ui.btn_divider_visible.toggled.connect(self.main_controller.toggle_divider_line_visibility)
        self.ui.btn_divider_color.clicked.connect(self._show_divider_color_picker)
        self.ui.btn_divider_width.valueChanged.connect(self.main_controller.set_divider_line_thickness)

        self.ui.btn_magnifier_divider_visible.toggled.connect(self.main_controller.toggle_magnifier_divider_visibility)
        self.ui.btn_magnifier_divider_color.clicked.connect(self._show_magnifier_divider_color_picker)
        self.ui.btn_magnifier_divider_width.valueChanged.connect(self.main_controller.set_magnifier_divider_thickness)

        self.ui.slider_size.valueChanged.connect(lambda v: self.main_controller.update_magnifier_size_relative(v / 100.0))
        self.ui.slider_capture.valueChanged.connect(lambda v: self.main_controller.update_capture_size_relative(v / 100.0))
        self.ui.slider_speed.valueChanged.connect(lambda v: self.main_controller.update_movement_speed(v / 10.0))

        self.ui.btn_color_picker.clicked.connect(self.ui_manager.toggle_font_settings_flyout)

        self.font_settings_flyout.closed.connect(self._on_font_flyout_closed)
        self.app_state.stateChanged.connect(self._on_app_state_changed)
        self.ui.combo_interpolation.currentIndexChanged.connect(self.main_controller.on_interpolation_changed)

        self.ui.combo_interpolation.clicked.connect(self._on_interpolation_combo_clicked)

        self.ui.combo_image1.clicked.connect(lambda: self.ui_manager.show_flyout(1))
        self.ui.combo_image2.clicked.connect(lambda: self.ui_manager.show_flyout(2))
        self.ui.help_button.clicked.connect(self.ui_manager.show_help_dialog)
        self.ui.btn_settings.clicked.connect(self.ui_manager.show_settings_dialog)
        self.ui.btn_quick_save.clicked.connect(self._quick_save_with_error_handling)
        self.ui.btn_save.clicked.connect(self._save_result_with_error_handling)
        self.font_settings_flyout.settings_changed.connect(self.main_controller.apply_font_settings)

        self.ui.combo_image1.wheelScrolledToIndex.connect(lambda index: self.main_controller.on_combobox_changed(1, index))
        self.ui.combo_image2.wheelScrolledToIndex.connect(lambda index: self.main_controller.on_combobox_changed(2, index))

        self.ui.combo_interpolation.wheelScrolledToIndex.connect(self.main_controller.on_interpolation_changed)

        def handle_load_button(image_number):
            self._open_image_dialog(image_number)

        self.ui.btn_image1.clicked.connect(lambda: handle_load_button(1))
        self.ui.btn_image2.clicked.connect(lambda: handle_load_button(2))

        self.ui.btn_diff_mode.triggered.connect(lambda action: self.main_controller.set_diff_mode(action.data()))
        self.ui.btn_channel_mode.triggered.connect(lambda action: self.main_controller.set_channel_view_mode(action.data()))

        self.ui.combo_image1.wheelScrolledToIndex.connect(lambda index: self.main_controller.on_combobox_changed(1, index))
        self.ui.combo_image2.wheelScrolledToIndex.connect(lambda index: self.main_controller.on_combobox_changed(2, index))

    def connect_event_handler_signals(self, event_handler):

        event_handler.mouse_press_event_on_image_label_signal.connect(self.image_label_handler.handle_mouse_press)
        event_handler.mouse_move_event_on_image_label_signal.connect(self.image_label_handler.handle_mouse_move)
        event_handler.mouse_release_event_on_image_label_signal.connect(self.image_label_handler.handle_mouse_release)
        event_handler.keyboard_press_event_signal.connect(self.image_label_handler.handle_key_press)
        event_handler.keyboard_release_event_signal.connect(self.image_label_handler.handle_key_release)
        event_handler.mouse_wheel_event_on_image_label_signal.connect(self.image_label_handler.handle_wheel_scroll)
        event_handler.drag_enter_event_signal.connect(self.window_handler.handle_drag_enter)
        event_handler.drag_move_event_signal.connect(self.window_handler.handle_drag_move)
        event_handler.drag_leave_event_signal.connect(self.window_handler.handle_drag_leave)
        event_handler.drop_event_signal.connect(self.window_handler.handle_drop)
        event_handler.resize_event_signal.connect(self.window_handler.handle_resize)
        event_handler.close_event_signal.connect(self.window_handler.handle_close)
        event_handler.mouse_press_event_signal.connect(self._handle_global_mouse_press)

    def _on_interpolation_combo_clicked(self):
        try:
            idx = getattr(self.ui.combo_interpolation, 'currentIndex', lambda: -1)()
            txt = getattr(self.ui.combo_interpolation, 'currentText', lambda: '')()
            pass
        except Exception:
            pass
        self.ui_manager.toggle_interpolation_flyout()

    def repopulate_flyouts(self):
        if self.ui_manager:
            self.ui_manager.repopulate_flyouts()

    def _handle_global_mouse_press(self, event):
        global_pos = event.globalPosition()
        def _close_popups():
            self.ui_manager.close_all_flyouts_if_needed(global_pos)

        QTimer.singleShot(0, _close_popups)

    def _on_font_flyout_closed(self):

        self.ui_manager._font_popup_open = False
        self.ui.btn_color_picker.setFlyoutOpen(False)

    def _apply_initial_settings_to_ui(self):
        self.ui.slider_size.setValue(int(self.app_state.magnifier_size_relative * 100))
        self.ui.slider_capture.setValue(int(self.app_state.capture_size_relative * 100))
        self.ui.slider_speed.setValue(int(self.app_state.movement_speed_per_sec * 10))

        self.ui.btn_orientation.setChecked(self.app_state.is_horizontal, emit_signal=False)
        self.ui.btn_magnifier_orientation.setChecked(self.app_state.magnifier_is_horizontal, emit_signal=False)
        self.ui.btn_magnifier.setChecked(self.app_state.use_magnifier, emit_signal=False)
        self.ui.btn_freeze.setChecked(self.app_state.freeze_magnifier, emit_signal=False)
        self.ui.btn_file_names.setChecked(self.app_state.include_file_names_in_saved, emit_signal=False)

        self.ui.btn_divider_visible.setChecked(not self.app_state.divider_line_visible, emit_signal=False)
        self.ui.btn_divider_width.set_value(self.app_state.divider_line_thickness)
        self.ui.btn_divider_color.set_color(self.app_state.divider_line_color)

        self.ui.btn_magnifier_divider_visible.setChecked(not self.app_state.magnifier_divider_visible, emit_signal=False)
        self.ui.btn_magnifier_divider_width.set_value(self.app_state.magnifier_divider_thickness)
        self.ui.btn_magnifier_divider_color.set_color(self.app_state.magnifier_divider_color)

        self.ui.toggle_edit_layout_visibility(self.app_state.include_file_names_in_saved)
        self.ui.toggle_magnifier_panel_visibility(self.app_state.use_magnifier)
        self._update_interpolation_combo_box_ui()
        self.update_file_names_display()
        self._setup_view_buttons()
        self.on_language_changed()

    def _on_app_state_changed(self):
        self.ui.toggle_magnifier_panel_visibility(self.app_state.use_magnifier)

        if self.ui.btn_orientation.isChecked() != self.app_state.is_horizontal:
            self.ui.btn_orientation.setChecked(self.app_state.is_horizontal, emit_signal=False)
        if self.ui.btn_magnifier_orientation.isChecked() != self.app_state.magnifier_is_horizontal:
            self.ui.btn_magnifier_orientation.setChecked(self.app_state.magnifier_is_horizontal, emit_signal=False)
        self.ui.toggle_edit_layout_visibility(self.app_state.include_file_names_in_saved)

        self.ui_batcher.schedule_batch_update(['file_names', 'resolution', 'combobox', 'slider_tooltips', 'ratings', 'window_schedule'])

    def _open_image_dialog(self, image_number: int):
        try:
            if self._file_dialog is not None and self._file_dialog.isVisible():
                try:
                    self._file_dialog.raise_()
                    self._file_dialog.activateWindow()
                except Exception:
                    pass
                return

            file_dialog = QFileDialog(self.main_window_app, tr("Select Image(s)", self.app_state.current_language))
            file_dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
            file_dialog.setNameFilter(f"{tr('Image Files', self.app_state.current_language)} (*.png *.bmp *.gif *.webp *.tif *.tiff);;{tr('All Files', self.app_state.current_language)} (*)")
            file_dialog.setWindowModality(Qt.WindowModality.NonModal)
            file_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

            self.main_window_app.theme_manager.apply_theme_to_dialog(file_dialog)

            def on_selected(paths: list[str]):
                if paths:
                    delay = 100 if getattr(self, "_first_dialog_load_pending", True) else 0
                    QTimer.singleShot(delay, lambda: self.main_controller.load_images_from_paths(paths, image_number))
                    self._first_dialog_load_pending = False

            file_dialog.filesSelected.connect(on_selected)
            file_dialog.destroyed.connect(lambda: setattr(self, "_file_dialog", None))
            self._file_dialog = file_dialog
            file_dialog.show()
            try:
                file_dialog.raise_()
                file_dialog.activateWindow()
            except Exception:
                pass
        except Exception:
            logger.exception("Failed to open non-modal file dialog")

    def update_resolution_labels(self):
        """Публичный метод - регистрирует обновление"""
        self.ui_batcher.schedule_update('resolution')

    def _do_update_resolution_labels(self):
        """Приватный метод - выполняет реальное обновление"""
        res1_text = "--x--"
        if dim := self.app_state.get_image_dimensions(1): res1_text = f"{dim[0]}x{dim[1]}"
        res2_text = "--x--"
        if dim := self.app_state.get_image_dimensions(2): res2_text = f"{dim[0]}x{dim[1]}"
        self.ui.update_resolution_labels(res1_text, res1_text, res2_text, res2_text)

        psnr_visible = self.app_state.auto_calculate_psnr
        self.ui.psnr_label.setVisible(psnr_visible)
        if psnr_visible:
            psnr = self.app_state.psnr_value
            if psnr is not None:
                self.ui.psnr_label.setText(f"PSNR: {psnr:.2f} dB")
            else:
                self.ui.psnr_label.setText("PSNR: --")

        ssim_visible = self.app_state.auto_calculate_ssim or self.app_state.diff_mode == 'ssim'
        self.ui.ssim_label.setVisible(ssim_visible)
        if ssim_visible:
            ssim = self.app_state.ssim_value
            if ssim is not None:
                self.ui.ssim_label.setText(f"SSIM: {ssim:.4f}")
            else:
                self.ui.ssim_label.setText("SSIM: --")

    def update_file_names_display(self):
        """Публичный метод - регистрирует обновление"""
        self.ui_batcher.schedule_update('file_names')

    def _do_update_file_names_display(self):
        """Приватный метод - выполняет реальное обновление"""
        name1 = self.app_state.get_current_display_name(1) or "-----"
        name2 = self.app_state.get_current_display_name(2) or "-----"

        self.ui.update_file_names_display(name1, name2, self.app_state.is_horizontal, self.app_state.current_language, True)
        self.check_name_lengths()

    def check_name_lengths(self):
        len1 = len(self.ui.edit_name1.text().strip())
        len2 = len(self.ui.edit_name2.text().strip())
        limit = self.app_state.max_name_length
        if (len1 > limit or len2 > limit) and self.app_state.include_file_names_in_saved:
            self.ui.update_name_length_warning(
                tr("Name length limit ({limit}) exceeded!", self.app_state.current_language).format(limit=limit),
                "", True)
        else:
            self.ui.update_name_length_warning("", "", False)

    def update_combobox_displays(self):
        """Публичный метод - регистрирует обновление"""
        self.ui_batcher.schedule_update('combobox')

    def _do_update_combobox_displays(self):
        """Приватный метод - выполняет реальное обновление"""
        count1 = len(self.app_state.image_list1)
        idx1 = self.app_state.current_index1
        text1 = self.app_state.get_current_display_name(1) if 0 <= idx1 < count1 else tr("Select an image", self.app_state.current_language)
        self.ui.update_combobox_display(1, count1, idx1, text1, "")

        count2 = len(self.app_state.image_list2)
        idx2 = self.app_state.current_index2
        text2 = self.app_state.get_current_display_name(2) if 0 <= idx2 < count2 else tr("Select an image", self.app_state.current_language)
        self.ui.update_combobox_display(2, count2, idx2, text2, "")

    def update_slider_tooltips(self):
        """Публичный метод - регистрирует обновление"""
        self.ui_batcher.schedule_update('slider_tooltips')

    def _do_update_slider_tooltips(self):
        """Приватный метод - выполняет реальное обновление"""
        self.ui.update_slider_tooltips(self.app_state.movement_speed_per_sec, self.app_state.magnifier_size_relative, self.app_state.capture_size_relative, self.app_state.current_language)

    def update_rating_displays(self):
        """Публичный метод - регистрирует обновление"""
        self.ui_batcher.schedule_update('ratings')

    def _do_update_rating_displays(self):
        """Приватный метод - выполняет реальное обновление"""
        self.ui.update_rating_display(1, self.app_state.get_current_score(1), self.app_state.current_language)
        self.ui.update_rating_display(2, self.app_state.get_current_score(2), self.app_state.current_language)

    def on_language_changed(self):
        self.ui.update_translations(self.app_state.current_language)
        self._setup_view_buttons()

        self._do_update_combobox_displays()

        self._update_interpolation_combo_box_ui()
        self.ui.reapply_button_styles()

    def _update_interpolation_combo_box_ui(self):

        try:
            from image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False

        method_keys_all = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
        method_keys = [k for k in method_keys_all if k != "EWA_LANCZOS" or WAND_AVAILABLE]

        target_method_key = self.app_state.interpolation_method
        if target_method_key not in method_keys:
            target_method_key = AppConstants.DEFAULT_INTERPOLATION_METHOD if AppConstants.DEFAULT_INTERPOLATION_METHOD in method_keys else (method_keys[0] if method_keys else AppConstants.DEFAULT_INTERPOLATION_METHOD)
            self.app_state.interpolation_method = target_method_key

        try:
            current_index = method_keys.index(target_method_key)
        except ValueError:
            current_index = 0

        labels = [
            tr(AppConstants.INTERPOLATION_METHODS_MAP[key], self.app_state.current_language)
            for key in method_keys
        ]
        display_text = labels[current_index] if 0 <= current_index < len(labels) else ""

        self.ui.combo_interpolation.updateState(
            count=len(method_keys),
            current_index=current_index,
            text=display_text,
            items=labels
        )

    def _setup_view_buttons(self):
        lang = self.app_state.current_language

        diff_actions = [
            (tr("Off", lang), 'off'),
            (tr("Highlight", lang), 'highlight'),
            (tr("Grayscale", lang), 'grayscale'),
            (tr("Edge Comparison", lang), 'edges'),
            (tr("SSIM Map", lang), 'ssim')
        ]
        self.ui.btn_diff_mode.set_actions(diff_actions)
        self.ui.btn_diff_mode.set_current_by_data(self.app_state.diff_mode)

        channel_actions = [
            (tr("RGB", lang), 'RGB'), ('Red', 'R'), ('Green', 'G'), ('Blue', 'B'),
            (tr("Luminance", lang), 'L')
        ]
        self.ui.btn_channel_mode.set_actions(channel_actions)
        self.ui.btn_channel_mode.set_current_by_data(self.app_state.channel_view_mode)

    def _finish_resize_delay(self):
        if self.app_state.resize_in_progress:
            self.app_state.resize_in_progress = False
            self.main_window_app.schedule_update()

    def _save_result_with_error_handling(self):
        if not self.app_state.original_image1 or not self.app_state.original_image2:
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=tr("Warning", self.app_state.current_language),
                text=tr("Please load and select images in both slots first.", self.app_state.current_language)
            )
            return

        try:
            original1_full = self.app_state.full_res_image1 or self.app_state.original_image1
            original2_full = self.app_state.full_res_image2 or self.app_state.original_image2

            if not original1_full or not original2_full: raise ValueError("Full resolution images are not available for saving.")
            image1_for_save, image2_for_save = resize_images_processor(original1_full, original2_full)
            if not image1_for_save or not image2_for_save: raise ValueError("Failed to unify images for saving.")

            save_width, save_height = image1_for_save.size

            magnifier_coords_for_save = get_magnifier_drawing_coords(
                app_state=self.app_state,
                drawing_width=save_width,
                drawing_height=save_height,
                container_width=save_width,
                container_height=save_height,
            ) if self.app_state.use_magnifier else None

            preview_scale = max(1, min(5, max(save_width, save_height) // 800))
            preview_w, preview_h = max(1, save_width // preview_scale), max(1, save_height // preview_scale)

            magnifier_coords_for_preview = get_magnifier_drawing_coords(
                app_state=self.app_state,
                drawing_width=preview_w,
                drawing_height=preview_h,
            ) if self.app_state.use_magnifier else None

            composer = ImageComposer(self.main_window_app.font_path_absolute)

            preview_img, _, _, _, _ = composer.generate_comparison_image(
                app_state=self.app_state,
                image1_scaled=image1_for_save.resize((preview_w, preview_h), PIL.Image.Resampling.BILINEAR),
                image2_scaled=image2_for_save.resize((preview_w, preview_h), PIL.Image.Resampling.BILINEAR),
                original_image1=original1_full,
                original_image2=original2_full,
                magnifier_drawing_coords=magnifier_coords_for_preview,
                font_path_absolute=self.main_window_app.font_path_absolute, file_name1_text=self.app_state.get_current_display_name(1),
                file_name2_text=self.app_state.get_current_display_name(2)
            )
            if preview_img is None:
                preview_img = PIL.Image.new("RGBA", (preview_w, preview_h), (200,200,200,255))

            name1 = (self.app_state.get_current_display_name(1) or "image1").strip()
            name2 = (self.app_state.get_current_display_name(2) or "image2").strip()
            def sanitize(s: str) -> str:
                s = re.sub(r'[\\/*?:"<>|]', "_", s)
                return s[:80]

            base_name = f"{sanitize(name1)}_{sanitize(name2)}"

            out_dir = self.app_state.export_default_dir or self.main_window_app._get_os_default_downloads()
            fmt = (self.app_state.export_last_format or "PNG").upper()
            ext = "." + fmt.lower().replace("jpeg", "jpg")

            unique_full_path = self._get_unique_filepath(out_dir, base_name, ext)
            unique_filename_without_ext = os.path.splitext(os.path.basename(unique_full_path))[0]

            result_code, export_opts = self.ui_manager.show_export_dialog(preview_img, suggested_filename=unique_filename_without_ext)
            if int(result_code) != int(QDialog.DialogCode.Accepted): return

            out_dir, out_name = export_opts.get("output_dir"), export_opts.get("file_name")
            if not out_dir or not out_name:
                self.ui_manager.show_non_modal_message(
                    icon=QMessageBox.Icon.Warning,
                    title=tr("Invalid Data", self.app_state.current_language),
                    text=tr("Please specify output directory and file name.", self.app_state.current_language)
                )
                return

            app_state_copy_for_task = self.app_state.copy_for_worker()
            save_task_id = self.main_window_app.save_task_counter
            self.main_window_app.save_task_counter += 1

            fmt_disp = (export_opts.get("format", "PNG") or "PNG").upper()
            ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
            final_path_for_display = os.path.join(out_dir, f"{out_name}{ext_disp}")
            toast_message = f"{tr('Saving', self.app_state.current_language)}\n{final_path_for_display}..."

            cancel_event = threading.Event()
            _cancel_ctx = {"event": cancel_event}
            def on_cancel():
                ev = _cancel_ctx.get("event")
                toast_id = _cancel_ctx.get("id")
                if ev: ev.set()
                if toast_id is not None:
                    self.main_window_app.toast_manager.update_toast(
                        toast_id, tr("Saving canceled", self.app_state.current_language), success=False, duration=3000,
                    )

            save_task_id = self.main_window_app.toast_manager.show_toast(
                toast_message, duration=0, action_text=tr("Cancel", self.app_state.current_language), on_action=on_cancel,
            )
            _cancel_ctx["id"] = save_task_id
            self._save_cancellation[save_task_id] = cancel_event

            worker = GenericWorker(
                self._export_worker_task,
                composer=composer,
                app_state_copy=app_state_copy_for_task,
                image1_for_save=image1_for_save,
                image2_for_save=image2_for_save,
                original1_full=original1_full,
                original2_full=original2_full,
                magnifier_drawing_coords=magnifier_coords_for_save,
                export_options=export_opts,
                cancel_event=cancel_event,
                file_name1_text=self.app_state.get_current_display_name(1),
                file_name2_text=self.app_state.get_current_display_name(2),
            )
            self._save_workers[save_task_id] = worker

            def _on_done(out_path):
                if cancel_event.is_set(): return
                success_message = f"{tr('Saved', self.app_state.current_language)} {os.path.basename(out_path)}"
                self.main_window_app.toast_manager.update_toast(save_task_id, success_message, success=True)
                try:
                    setattr(self.main_window_app, "_last_saved_path", out_path)
                    if hasattr(self.main_window_app, "update_tray_actions_visibility"): self.main_window_app.update_tray_actions_visibility()
                    tray = getattr(self.main_window_app, "tray_icon", None)
                    if tray and tray.isVisible() and getattr(self.app_state, "system_notifications_enabled", True):
                        image_for_icon = out_path if isinstance(out_path, str) and os.path.isfile(out_path) else None
                        self.main_window_app.notify_system(tr("Saved", self.app_state.current_language), f"{tr('Saved:', self.app_state.current_language)} {out_path}", image_path=image_for_icon, timeout_ms=4000)
                except Exception as e: logger.error(f"Tray notification error: {e}")
                finally:
                    self._save_cancellation.pop(save_task_id, None)
                    self._save_workers.pop(save_task_id, None)

            def _on_err(err_tuple):
                if not cancel_event.is_set():
                    error_message = f"{tr('Error saving', self.app_state.current_language)} {final_path_for_display}"
                    self.main_window_app.toast_manager.update_toast(save_task_id, error_message, success=False, duration=8000)
                self._save_cancellation.pop(save_task_id, None)
                self._save_workers.pop(save_task_id, None)

            worker.signals.result.connect(_on_done)
            worker.signals.error.connect(_on_err)
            self.main_window_app.thread_pool.start(worker)

            self.app_state.export_last_format = export_opts.get("format", "PNG")
            self.app_state.export_quality = int(export_opts.get("quality", 95))
            self.app_state.export_fill_background = bool(export_opts.get("fill_background", False))
            bg_c = export_opts.get("background_color")
            self.app_state.export_background_color = QColor(bg_c[0], bg_c[1], bg_c[2], bg_c[3])
            self.app_state.export_last_filename = out_name
            self.app_state.export_default_dir = out_dir
            self.app_state.export_png_compress_level = int(export_opts.get("png_compress_level", 9))

            if bool(export_opts.get("comment_keep_default", False)):
                self.app_state.export_comment_text = export_opts.get("comment_text", "")
                self.app_state.export_comment_keep_default = True
            else:
                self.app_state.export_comment_text = ""
                self.app_state.export_comment_keep_default = False
            self.main_controller.settings_manager.save_all_settings(self.app_state)
        except Exception as e:
            logger.error(f"Error during save preparation: {e}", exc_info=True)
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=tr("Error", self.app_state.current_language),
                text=f"{tr('Failed to save image:', self.app_state.current_language)}\n{str(e)}"
            )

    def _quick_save_with_error_handling(self):
        if not self.app_state.original_image1 or not self.app_state.original_image2:
            self.ui_manager.show_non_modal_message(icon=QMessageBox.Icon.Warning, title=tr("Warning", self.app_state.current_language), text=tr("Please load and select images in both slots first.", self.app_state.current_language))
            return

        if not hasattr(self.app_state, 'export_default_dir') or not self.app_state.export_default_dir:
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Warning,
                title=tr("Warning", self.app_state.current_language),
                text=tr("No previous export settings found. Please use Save Result first.", self.app_state.current_language)
            )
            return

        try:
            original1_full = self.app_state.full_res_image1 or self.app_state.original_image1
            original2_full = self.app_state.full_res_image2 or self.app_state.original_image2

            if not original1_full or not original2_full:
                raise ValueError("Full resolution images are not available for saving.")

            image1_for_save, image2_for_save = resize_images_processor(original1_full, original2_full)
            if not image1_for_save or not image2_for_save:
                raise ValueError("Failed to unify images for saving.")

            save_width, save_height = image1_for_save.size

            magnifier_coords_for_save = get_magnifier_drawing_coords(
                app_state=self.app_state,
                drawing_width=save_width,
                drawing_height=save_height,
                container_width=save_width,
                container_height=save_height,
            ) if self.app_state.use_magnifier else None

            composer = ImageComposer(self.main_window_app.font_path_absolute)
            app_state_copy_for_task = self.app_state.copy_for_worker()

            bg_color_qcolor = getattr(self.app_state, 'export_background_color', QColor(255, 255, 255, 255))
            bg_color_tuple = (bg_color_qcolor.red(), bg_color_qcolor.green(), bg_color_qcolor.blue(), bg_color_qcolor.alpha())

            name1 = (self.app_state.get_current_display_name(1) or "image1").strip()
            name2 = (self.app_state.get_current_display_name(2) or "image2").strip()
            def sanitize(s: str) -> str:
                s = re.sub(r'[\\/*?:"<>|]', "_", s)
                return s[:80]

            base_name = f"{sanitize(name1)}_{sanitize(name2)}"

            export_options = {
                "output_dir": self.app_state.export_default_dir,
                "file_name": base_name,
                "format": self.app_state.export_last_format or "PNG",
                "quality": self.app_state.export_quality or 95,
                "fill_background": getattr(self.app_state, 'export_fill_background', False),
                "background_color": bg_color_tuple,
                "png_compress_level": getattr(self.app_state, 'export_png_compress_level', 9),
                "png_optimize": True,
                "include_metadata": bool(getattr(self.app_state, 'export_comment_keep_default', False)),
                "comment_text": (getattr(self.app_state, 'export_comment_text', '') if getattr(self.app_state, 'export_comment_keep_default', False) else ''),
                "is_quick_save": True,
            }

            save_task_id = self.main_window_app.save_task_counter
            self.main_window_app.save_task_counter += 1

            fmt_disp = (export_options.get("format", "PNG") or "PNG").upper()
            ext_disp = "." + fmt_disp.lower().replace("jpeg", "jpg")
            display_path = os.path.join(export_options.get("output_dir"), f"{export_options.get('file_name')}{ext_disp}")
            toast_message = f"{tr('Saving', self.app_state.current_language)}\n{display_path}..."

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
                        tr("Saving canceled", self.app_state.current_language),
                        success=False,
                        duration=3000,
                    )
            save_task_id = self.main_window_app.toast_manager.show_toast(
                toast_message,
                duration=0,
                action_text=tr("Cancel", self.app_state.current_language),
                on_action=on_cancel_quick,
            )
            _cancel_ctx["id"] = save_task_id
            self._save_cancellation[save_task_id] = cancel_event

            worker = GenericWorker(
                self._export_worker_task,
                composer=composer,
                app_state_copy=app_state_copy_for_task,
                image1_for_save=image1_for_save,
                image2_for_save=image2_for_save,
                original1_full=original1_full,
                original2_full=original2_full,
                magnifier_drawing_coords=magnifier_coords_for_save,
                export_options=export_options,
                cancel_event=cancel_event,
                file_name1_text=self.app_state.get_current_display_name(1),
                file_name2_text=self.app_state.get_current_display_name(2),
            )
            self._save_workers[save_task_id] = worker

            def _on_done(out_path):
                if cancel_event.is_set():
                    return
                success_message = f"{tr('Saved', self.app_state.current_language)} {os.path.basename(out_path)}"
                self.main_window_app.toast_manager.update_toast(save_task_id, success_message, success=True)
                try:
                    setattr(self.main_window_app, "_last_saved_path", out_path)
                    if hasattr(self.main_window_app, "update_tray_actions_visibility"):
                        self.main_window_app.update_tray_actions_visibility()
                    tray = getattr(self.main_window_app, "tray_icon", None)
                    if getattr(self.app_state, "system_notifications_enabled", True):
                        image_for_icon = out_path if isinstance(out_path, str) and os.path.isfile(out_path) else None
                        self.main_window_app.notify_system(
                            tr("Saved", self.app_state.current_language),
                            f"{tr('Saved:', self.app_state.current_language)} {out_path}",
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
                    error_message = f"{tr('Error saving', self.app_state.current_language)} {display_path}"
                    self.main_window_app.toast_manager.update_toast(save_task_id, error_message, success=False, duration=8000)
                self._save_cancellation.pop(save_task_id, None)
                self._save_workers.pop(save_task_id, None)

            worker.signals.result.connect(_on_done)
            worker.signals.error.connect(_on_err)
            self.main_window_app.thread_pool.start(worker)

        except Exception as e:
            logger.error(f"Error during quick save preparation: {e}", exc_info=True)
            self.ui_manager.show_non_modal_message(
                icon=QMessageBox.Icon.Critical,
                title=tr("Error", self.app_state.current_language),
                text=f"{tr('Failed to quick save image:', self.app_state.current_language)}\n{str(e)}"
            )

    def _export_worker_task(self, **kwargs):
        composer = kwargs['composer']
        progress_callback = kwargs.get('progress_callback')
        cancel_event = kwargs.get('cancel_event')

        def emit_progress(val):
            if progress_callback: progress_callback.emit(val)

        def check_canceled():
            if cancel_event and cancel_event.is_set(): raise RuntimeError("Save canceled by user")

        try:
            emit_progress(10)
            check_canceled()
            final_img, _, _, _, _ = composer.generate_comparison_image(
                app_state=kwargs['app_state_copy'],
                image1_scaled=kwargs['image1_for_save'],
                image2_scaled=kwargs['image2_for_save'],
                original_image1=kwargs['original1_full'],
                original_image2=kwargs['original2_full'],
                magnifier_drawing_coords=kwargs.get('magnifier_drawing_coords'),
                font_path_absolute=self.main_window_app.font_path_absolute,
                file_name1_text=kwargs['file_name1_text'],
                file_name2_text=kwargs['file_name2_text'],
            )
            if final_img is None: raise ValueError("Failed to create the base image for saving.")
            emit_progress(50)
            check_canceled()

            export_options = kwargs['export_options']
            img_to_save = final_img
            if export_options.get("fill_background", False):
                bg_color_tuple = export_options.get("background_color")
                bg = PIL.Image.new("RGBA", final_img.size, bg_color_tuple)
                bg.paste(final_img, mask=final_img.split()[3] if final_img.mode == "RGBA" else None)
                img_to_save = bg

            emit_progress(60)
            check_canceled()

            target_format = export_options.get("format", "PNG").upper()
            pil_format = "JPEG" if target_format == "JPG" else target_format
            output_dir = export_options.get("output_dir")
            base_name = export_options.get("file_name")
            is_quick_save = export_options.get("is_quick_save", False)
            ext = f".{target_format.lower().replace('jpeg', 'jpg')}"

            if is_quick_save:

                full_path = self._get_unique_filepath(output_dir, base_name, ext)
            else:

                full_path = os.path.join(output_dir, f"{base_name}{ext}")

            os.makedirs(output_dir, exist_ok=True)
            save_kwargs = {}
            formats_with_alpha = {"PNG", "TIFF", "WEBP"}
            if pil_format not in formats_with_alpha and img_to_save.mode == 'RGBA':
                bg_color_tuple = export_options.get("background_color") or (255, 255, 255, 255)
                bg_flat = PIL.Image.new("RGBA", img_to_save.size, bg_color_tuple)
                bg_flat.paste(img_to_save, mask=img_to_save.split()[3])
                img_to_save = bg_flat.convert('RGB')

            if pil_format == "JPEG":
                save_kwargs['quality'] = int(export_options.get("quality", 95))
                try:
                    comment_text = (export_options.get("comment_text") or "").strip()
                    if comment_text and bool(export_options.get("include_metadata", True)):
                        exif = img_to_save.getexif()
                        exif[0x9286] = comment_text
                        save_kwargs['exif'] = exif.tobytes()
                except Exception: pass
            elif pil_format == "PNG":
                save_kwargs['compress_level'] = int(export_options.get("png_compress_level", 9))
                save_kwargs['optimize'] = bool(export_options.get("png_optimize", True))
                try:
                    comment_text = (export_options.get("comment_text") or "").strip()
                    if comment_text and bool(export_options.get("include_metadata", True)):
                        import PIL.PngImagePlugin as PngImagePlugin
                        meta = PngImagePlugin.PngInfo()
                        meta.add_text("Comment", comment_text)
                        save_kwargs['pnginfo'] = meta
                except Exception: pass

            check_canceled()

            class _CancelableStream:
                def __init__(self, base, cancel_ev): self._b, self._e = base, cancel_ev
                def write(self, b):
                    if self._e and self._e.is_set(): raise RuntimeError("Save canceled by user")
                    return self._b.write(b)
                def flush(self): return self._b.flush()
                def close(self): return self._b.close()
                def seek(self, *args, **kwargs): return self._b.seek(*args, **kwargs)
                def tell(self): return self._b.tell()
                def writable(self): return True
                def readable(self): return False
                def seekable(self): return True
                def fileno(self): return self._b.fileno()

            try:
                with open(full_path, 'wb') as _raw:
                    _stream = _CancelableStream(_raw, cancel_event)
                    img_to_save.save(_stream, format=pil_format, **save_kwargs)
            except Exception:
                try:
                    if os.path.exists(full_path): os.remove(full_path)
                except Exception: pass
                raise

            check_canceled()
            emit_progress(100)
            return full_path
        except Exception as e:
            if isinstance(e, RuntimeError) and str(e) == "Save canceled by user": return None
            logger.error(f"Export worker task failed: {e}", exc_info=True)
            raise e

    def get_current_label_dimensions(self) -> tuple[int, int]:
        if hasattr(self.ui, "image_label"):
            size = self.ui.image_label.size()
            return (size.width(), size.height())
        return (0, 0)

    def update_minimum_window_size(self):
        layout = self.main_window_app.layout()
        if not layout or not hasattr(self.ui, "image_label"): return

        original_policy = self.ui.image_label.sizePolicy()
        temp_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(QSizePolicy.Policy.Preferred if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)
        temp_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)

        try:
            self.ui.image_label.setSizePolicy(temp_policy)
            self.ui.image_label.updateGeometry()
            if layout:
                layout.invalidate()
                layout.activate()

            layout_hint_size = layout.sizeHint() if layout else QSize(250, 300)
            base_min_w, base_min_h = (250, 300)
            new_min_w, new_min_h = (max(base_min_w, layout_hint_size.width()), max(base_min_h, layout_hint_size.height()))
            padding = 10
            new_min_w += padding
            new_min_h += padding
            current_min = self.main_window_app.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.main_window_app.setMinimumSize(new_min_w, new_min_h)
        finally:
            if (hasattr(self.ui, "image_label") and self.ui.image_label.sizePolicy() != original_policy):
                self.ui.image_label.setSizePolicy(original_policy)
                self.ui.image_label.updateGeometry()
                if layout:
                    layout.invalidate()
                    layout.activate()

    def _quick_save_with_settings(self, output_path: str) -> bool:
        if not self.app_state.original_image1 or not self.app_state.original_image2:
            QMessageBox.warning(self.main_window_app, tr("Warning", self.app_state.current_language), tr("Please load and select images in both slots first.", self.app_state.current_language))
            return False

        try:
            original1_full = self.app_state.full_res_image1 or self.app_state.original_image1
            original2_full = self.app_state.full_res_image2 or self.app_state.original_image2

            if not original1_full or not original2_full:
                raise ValueError("Full resolution images are not available for saving.")

            image1_for_save, image2_for_save = resize_images_processor(original1_full, original2_full)
            if not image1_for_save or not image2_for_save:
                raise ValueError("Failed to unify images for saving.")

            save_width, save_height = image1_for_save.size

            composer = ImageComposer(self.main_window_app.font_path_absolute)

            final_img, _, _, _, _ = composer.generate_comparison_image(
                app_state=self.app_state,
                image1_scaled=image1_for_save,
                image2_scaled=image2_for_save,
                original_image1=original1_full,
                original_image2=original2_full,
                magnifier_drawing_coords=None,
                font_path_absolute=self.main_window_app.font_path_absolute,
                file_name1_text=self.app_state.get_current_display_name(1),
                file_name2_text=self.app_state.get_current_display_name(2)
            )

            if final_img is None:
                raise ValueError("Failed to create the base image for saving.")

            img_to_save = final_img
            if hasattr(self.app_state, 'export_fill_background') and self.app_state.export_fill_background:
                if hasattr(self.app_state, 'export_background_color') and self.app_state.export_background_color:
                    bg_color = self.app_state.export_background_color
                    bg_color_tuple = (bg_color.red(), bg_color.green(), bg_color.blue(), bg_color.alpha())
                    bg = PIL.Image.new("RGBA", final_img.size, bg_color_tuple)
                    bg.paste(final_img, mask=final_img.split()[3] if final_img.mode == "RGBA" else None)
                    img_to_save = bg

            target_format = getattr(self.app_state, 'export_last_format', 'PNG').upper()
            pil_format = "JPEG" if target_format == "JPG" else target_format

            save_kwargs = {}

            formats_with_alpha = {"PNG", "TIFF", "WEBP"}
            if pil_format not in formats_with_alpha and img_to_save.mode == 'RGBA':
                bg_color = getattr(self.app_state, 'export_background_color', None)
                if bg_color is not None:
                    bg_tuple = (bg_color.red(), bg_color.green(), bg_color.blue(), bg_color.alpha())
                else:
                    bg_tuple = (255, 255, 255, 255)
                bg_flat = PIL.Image.new("RGBA", img_to_save.size, bg_tuple)
                bg_flat.paste(img_to_save, mask=img_to_save.split()[3])
                img_to_save = bg_flat.convert('RGB')

            if pil_format == "JPEG":
                save_kwargs['quality'] = getattr(self.app_state, 'export_quality', 95)
            elif pil_format == "PNG":
                save_kwargs['compress_level'] = getattr(self.app_state, 'export_png_compress_level', 9)
                save_kwargs['optimize'] = True

            output_dir = os.path.dirname(output_path)
            os.makedirs(output_dir, exist_ok=True)

            img_to_save.save(output_path, format=pil_format, **save_kwargs)

            try:
                if hasattr(self.main_window_app, "update_tray_actions_visibility"):
                    self.main_window_app.update_tray_actions_visibility()
                tray = getattr(self.main_window_app, "tray_icon", None)
                if getattr(self.app_state, "system_notifications_enabled", True):
                    image_for_icon = output_path if isinstance(output_path, str) and os.path.isfile(output_path) else None
                    self.main_window_app.notify_system(
                        tr("Saved", self.app_state.current_language),
                        f"{tr('Saved:', self.app_state.current_language)} {output_path}",
                        image_path=image_for_icon,
                        timeout_ms=4000,
                    )
            except Exception as e:
                logger.error(f"Tray notification error: {e}")

            return True

        except Exception as e:
            logger.error(f"Error during quick save: {e}", exc_info=True)
            QMessageBox.critical(self.main_window_app, tr("Error", self.app_state.current_language), f"{tr('Failed to save image:', self.app_state.current_language)}\n{str(e)}")
            return False

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

    def _show_divider_color_picker(self):
        """Показывает диалог выбора цвета для линии разделения"""
        from PyQt6.QtWidgets import QColorDialog
        if self._divider_color_dialog and self._divider_color_dialog.isVisible():
            self._divider_color_dialog.raise_()
            self._divider_color_dialog.activateWindow()
            return

        current_color = self.app_state.divider_line_color
        self._divider_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._divider_color_dialog.setWindowFlags(self._divider_color_dialog.windowFlags() | Qt.WindowType.Window)
        self._divider_color_dialog.setModal(False)
        self._divider_color_dialog.setWindowTitle(tr("Choose Divider Line Color", self.app_state.current_language))
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._divider_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                self.main_controller.set_divider_line_color(color)
                self.ui.btn_divider_color.set_color(color)

        self._divider_color_dialog.colorSelected.connect(on_color_selected)
        self._divider_color_dialog.show()

    def _show_magnifier_divider_color_picker(self):
        """Показывает диалог выбора цвета для внутренней линии разделения в лупе"""
        from PyQt6.QtWidgets import QColorDialog
        if self._magnifier_divider_color_dialog and self._magnifier_divider_color_dialog.isVisible():
            self._magnifier_divider_color_dialog.raise_()
            self._magnifier_divider_color_dialog.activateWindow()
            return

        current_color = self.app_state.magnifier_divider_color
        self._magnifier_divider_color_dialog = QColorDialog(current_color, self.main_window_app)
        self._magnifier_divider_color_dialog.setWindowFlags(self._magnifier_divider_color_dialog.windowFlags() | Qt.WindowType.Window)
        self._magnifier_divider_color_dialog.setModal(False)
        self._magnifier_divider_color_dialog.setWindowTitle(tr("Choose Magnifier Divider Line Color", self.app_state.current_language))
        self.main_window_app.theme_manager.apply_theme_to_dialog(self._magnifier_divider_color_dialog)

        def on_color_selected(color):
            if color.isValid():
                self.main_controller.set_magnifier_divider_color(color)
                self.ui.btn_magnifier_divider_color.set_color(color)

        self._magnifier_divider_color_dialog.colorSelected.connect(on_color_selected)
        self._magnifier_divider_color_dialog.show()

    def update_magnifier_orientation_button_state(self):
        """Обновляет состояние кнопки ориентации лупы извне."""
        self.ui.btn_magnifier_orientation.setChecked(self.app_state.magnifier_is_horizontal, emit_signal=False)

    def _toggle_magnifier_orientation_on_right_click(self):
        """Обрабатывает правый клик по основной кнопке ориентации и показывает попап."""

        self.main_controller.toggle_magnifier_orientation()

        is_now_horizontal = self.app_state.magnifier_is_horizontal
        icon_to_show = AppIcon.HORIZONTAL_SPLIT if is_now_horizontal else AppIcon.VERTICAL_SPLIT

        pixmap = get_app_icon(icon_to_show).pixmap(QSize(20, 20), QIcon.Mode.Normal, QIcon.State.Off)

        if self._orientation_popup is None:
            self._orientation_popup = QLabel(parent=self.main_window_app.window())
            self._orientation_popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
            self._orientation_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)

        is_dark = self.main_window_app.theme_manager.is_dark()
        bg_color = "#3c3c3c" if is_dark else "#ffffff"
        border_color = "#666666" if is_dark else "#d0d0d0"
        self._orientation_popup.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 4px;
            }}
        """)

        self._orientation_popup.setPixmap(pixmap)
        self._orientation_popup.setFixedSize(32, 32)

        button_global_pos = self.ui.btn_orientation.mapToGlobal(QPoint(0, 0))
        popup_x = button_global_pos.x() + (self.ui.btn_orientation.width() - self._orientation_popup.width()) // 2
        popup_y = button_global_pos.y() - self._orientation_popup.height() - 10

        self._orientation_popup.move(popup_x, popup_y)
        self._orientation_popup.show()
        self._orientation_popup.raise_()

        self._popup_timer.start(1200)

    def _hide_orientation_popup(self):
        """Скрывает всплывающую подсказку"""
        if self._orientation_popup:
            self._orientation_popup.hide()

